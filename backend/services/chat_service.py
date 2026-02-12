import json
import logging
import re
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Literal, Optional, Tuple

from fastapi import Request
from pydantic import BaseModel, Field
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from backend.services.rag.pipeline import build_context, format_sources

logger = logging.getLogger(__name__)

Intent = Literal["CASUAL", "LEGAL"]
Lang = Literal["norwegian", "english"]

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_BLANKLINE_RE = re.compile(r"\n{3,}")         
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")    


def normalize_stream_text(text: str) -> str:
    """
    Backend normalization for streamed text:
    - collapse 3+ newlines -> 2 newlines
    - remove trailing spaces before newline
    """
    if not text:
        return ""
    text = _TRAILING_WS_RE.sub("\n", text)
    text = _BLANKLINE_RE.sub("\n\n", text)
    return text

def _normalize_stream_with_carry(buf: str, carry: str = "", max_carry: int = 200) -> tuple[str, str]:
    """
    Prevent chunk-boundary blankline explosions.
    Keep a small tail in carry; emit only safe part.
    """
    combined = (carry or "") + (buf or "")
    if not combined:
        return "", ""

    if len(combined) <= max_carry:
        # keep in carry until we have enough to safely emit
        return "", normalize_stream_text(combined)

    safe = combined[:-max_carry]
    tail = combined[-max_carry:]

    safe = normalize_stream_text(safe)
    # keep tail raw-ish but trimmed for safety
    tail = normalize_stream_text(tail)
    return safe, tail

def _json_dumps(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)


def likely_language(query: str) -> Lang:
    q = (query or "").lower()
    if any(ch in q for ch in ["æ", "ø", "å"]) or any(w in q.split() for w in ["lov", "rett", "plikter", "hva", "hvordan"]):
        return "norwegian"
    return "english"


def _strip_urls(buf: str) -> str:
    return _URL_RE.sub("", buf or "")


def _dedupe_results_keep_order(results: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for r in results or []:
        chunk_id = r.get("chunk_id")
        if chunk_id:
            key = ("chunk_id", str(chunk_id))
        else:
            file_name = (r.get("file_name") or "").strip()
            chunk_index = r.get("chunk_index")
            parent_title = (r.get("parent_title") or "").strip()
            text = (r.get("text") or "").strip()
            key = ("fallback", file_name, chunk_index, parent_title, text[:120])

        if key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) >= k:
            break
    return out


def _is_query_relevant(results: List[Dict[str, Any]], min_score_threshold: float = 0.30, min_top3_avg: float = 0.40) -> bool:
    if not results:
        return False

    best_score = float(results[0].get("score", 0.0))
    if best_score < min_score_threshold:
        logger.info(f"Query likely irrelevant: best_score={best_score:.4f} < threshold={min_score_threshold}")
        return False

    top_3_scores = [float(r.get("score", 0.0)) for r in results[:3]]
    avg_score = sum(top_3_scores) / len(top_3_scores) if top_3_scores else 0.0
    if avg_score < min_top3_avg:
        logger.info(f"Query likely irrelevant: top3_avg={avg_score:.4f} < threshold={min_top3_avg}")
        return False

    return True


class RouteDecision(BaseModel):
    intent: Intent = Field(...)
    language: Lang = Field(...)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(default="")


ROUTER_SYSTEM = """You are a strict router for a Norwegian company law assistant.
Return JSON ONLY with keys: intent, language, confidence, reason.

intent: CASUAL|LEGAL
language: norwegian|english
confidence: 0..1
reason: short

CASUAL: greeting/thanks/bye/small talk.
LEGAL: any legal question or request for legal explanation.
No extra keys. No prose."""

router_prompt = ChatPromptTemplate.from_messages([("system", ROUTER_SYSTEM), ("user", "{query}")])

LEGAL_SYSTEM = """You are a Norwegian-based legal assistant specialized in Norwegian COMPANY LAW.

Scope:
- Answer ONLY about Norwegian law (related Norwegian company-law regulations).
- If the user asks about other countries' laws or unrelated topics: say you cannot help and ask them to reframe to Norwegian law.

Sources policy:
- If SOURCES are relevant: use them and cite Norwegian act + section when explicitly supported by the excerpts.
- If SOURCES are missing/insufficient: you MAY answer using general legal knowledge at a high level, but:
  - Do NOT invent section numbers or citations.
  - Clearly say that the answer is general and not directly supported by the provided Lovdata excerpts.
  - Answer only for Norwegian law, even if the question is about another jurisdiction.

Output rules:
- Output language MUST be exactly {language}.
- Do not include URLs in the answer text.
- Keep it structured and precise. No hallucinated citations.

Response structure:
- If the question is within scope and relevant sources are provided, use them to answer with specific references.
- If the question is within scope but no relevant sources are provided, answer based on general legal knowledge and clearly state the lack of direct sources.
- If the question is out of scope (not about Norwegian law), do NOT answer the question, but politely inform the user that you can only assist with Norwegian law and ask them to reframe their question accordingly.
- Always keep the answer focused on Norwegian law, regardless of the question's original scope.
- Answer with the retrieved sources along with the general knowlegde and answer in detail, but do not hallucinate citations or section numbers. If the sources are not sufficient to answer, clearly state that and answer based on general legal knowledge without citing specific sections. Do not include any information about other jurisdictions, even if the question is about them. Always respond in the specified language and do not include URLs in the answer.
"""

legal_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", LEGAL_SYSTEM),
        ("user", "SOURCES:\n{context}\n\nQUESTION:\n{query}"),
    ]
)

CASUAL_RESP = {
    "norwegian": "Hei! Hvordan kan jeg hjelpe deg med norsk selskapsrett i dag?",
    "english": "Hi! How can I help you with Norwegian company law today?",
}

OUT_OF_SCOPE_RESP = {
    "norwegian": "Jeg er spesialisert i norsk selskapsrett og kan dessverre ikke hjelpe med dette emnet. Spør gjerne om noe innen norsk selskapsrett.",
    "english": "I specialize in Norwegian company law and cannot help with this topic. Please ask something within Norwegian company law.",
}

NO_SOURCES_RESP = {
    "norwegian": "Jeg finner ingen relevante juridiske utdrag i Lovdata som direkte svarer på dette. Kan du presisere hvilken lov/paragraf eller hvilket aspekt av norsk selskapsrett du spør om?",
    "english": "I cannot find relevant legal excerpts in Lovdata that directly answer this. Could you specify which law/section or aspect of Norwegian company law you're asking about?",
}


class ChatService:
    def __init__(self, llm: AzureChatOpenAI, max_context_chars: int):
        self.llm = llm
        self.max_context_chars = max_context_chars
        self.router = router_prompt | self.llm.with_structured_output(RouteDecision)

    async def route(self, query: str, correlation_id: str) -> RouteDecision:
        fallback_lang = likely_language(query)
        try:
            decision: RouteDecision = await self.router.ainvoke({"query": query})
            if decision.confidence < 0.7:
                decision.language = fallback_lang
            logger.info(f"[{correlation_id}] routed intent={decision.intent} lang={decision.language} conf={decision.confidence}")
            return decision
        except Exception as e:
            logger.info(f"[{correlation_id}] router failed; fallback LEGAL ({type(e).__name__})")
            return RouteDecision(intent="LEGAL", language=fallback_lang, confidence=0.2, reason="router fallback")

    async def stream(
        self,
        query: str,
        retriever_fn: Callable[[List[float]], List[Dict[str, Any]]],
        embedder_fn: Callable[[str], Any],
        cache_get_fn: Callable[[str], Any],
        cache_set_fn: Callable[[str, Dict[str, Any]], None],
        cache_key: str,
        top_k: int,
        include_sources: bool,
        temperature: float,
        correlation_id: str,
        request: Optional[Request] = None,
    ) -> AsyncIterator[str]:
        t0 = time.time()
        decision = await self.route(query, correlation_id)

        def sse(obj: dict) -> str:
            return f"data: {_json_dumps(obj)}\n\n"

        async def emit_text(text: str, chunk_size: int = 48):
            # chunked token streaming (not per-char)
            text = text or ""
            for i in range(0, len(text), chunk_size):
                if request is not None:
                    try:
                        if await request.is_disconnected():
                            return
                    except Exception:
                        pass
                yield sse({"type": "token", "data": text[i : i + chunk_size]})

        # Always start by clearing sources in UI (critical)
        yield sse({"type": "sources", "data": []})

        # CASUAL
        if decision.intent == "CASUAL":
            msg = CASUAL_RESP.get(decision.language, CASUAL_RESP["english"])
            async for evt in emit_text(msg):
                yield evt
            meta = {
                "intent": "CASUAL",
                "language": decision.language,
                "confidence": decision.confidence,
                "chunks_retrieved": 0,
                "context_chars": 0,
                "estimated_tokens": 0,
                "query_time": round(time.time() - t0, 4),
                "cached": False,
            }
            yield sse({"type": "complete", "metadata": meta})
            return

        # CACHE (LEGAL)
        cached = cache_get_fn(cache_key)
        if cached:
            # if cached sources are not requested, keep them empty (already cleared)
            sources = cached.get("sources", []) if include_sources else []
            answer = cached.get("answer", "")
            
            answer = normalize_stream_text(answer)

            # emit sources only if requested and present
            if include_sources and sources:
                yield sse({"type": "sources", "data": sources})

            async for evt in emit_text(answer):
                yield evt

            meta = cached.get("metadata", {}) or {}
            meta["cached"] = True
            meta["query_time"] = round(time.time() - t0, 4)
            yield sse({"type": "complete", "metadata": meta})
            return

        # EMBED + RETRIEVE
        q = (query or "").strip()
        if not q:
            msg = NO_SOURCES_RESP.get(decision.language, NO_SOURCES_RESP["english"])
            async for evt in emit_text(msg):
                yield evt
            meta = {
                "intent": "LEGAL",
                "language": decision.language,
                "confidence": decision.confidence,
                "chunks_retrieved": 0,
                "context_chars": 0,
                "estimated_tokens": 0,
                "query_time": round(time.time() - t0, 4),
                "cached": False,
                "note": "empty_query",
            }
            yield sse({"type": "complete", "metadata": meta})
            return

        logger.info(f"[{correlation_id}] embedding")
        embedding = await embedder_fn(q)

        logger.info(f"[{correlation_id}] retrieving top_k={top_k}")
        raw_results: List[Dict[str, Any]] = retriever_fn(embedding) or []
        results = _dedupe_results_keep_order(raw_results, k=top_k)

        # If retrieval is weak/irrelevant -> do NOT show sources
        if results and not _is_query_relevant(results, min_score_threshold=0.30, min_top3_avg=0.40):
            msg = NO_SOURCES_RESP.get(decision.language, NO_SOURCES_RESP["english"])
            async for evt in emit_text(msg):
                yield evt
            meta = {
                "intent": "LEGAL",
                "language": decision.language,
                "confidence": decision.confidence,
                "chunks_retrieved": 0,
                "context_chars": 0,
                "estimated_tokens": 0,
                "query_time": round(time.time() - t0, 4),
                "cached": False,
                "note": "irrelevant_query",
            }
            yield sse({"type": "complete", "metadata": meta})
            return

        if not results:
            msg = NO_SOURCES_RESP.get(decision.language, NO_SOURCES_RESP["english"])
            async for evt in emit_text(msg):
                yield evt
            meta = {
                "intent": "LEGAL",
                "language": decision.language,
                "confidence": decision.confidence,
                "chunks_retrieved": 0,
                "context_chars": 0,
                "estimated_tokens": 0,
                "query_time": round(time.time() - t0, 4),
                "cached": False,
                "note": "no_sources",
            }
            yield sse({"type": "complete", "metadata": meta})
            return

        # BUILD CONTEXT
        context, ctx_meta = build_context(results, max_chars=self.max_context_chars)

        # Prepare sources ONLY from Milvus results
        sources = format_sources(results, k=3) if include_sources else []

        # Emit sources only when we actually proceed with answering
        if include_sources and sources:
            yield sse({"type": "sources", "data": sources})
        else:
            # keep cleared []
            pass

        # GENERATE (TRUE STREAM)
        llm = self.llm.bind(temperature=float(temperature))
        chain = legal_prompt | llm

        full_answer = ""

        carry = ""

        async for chunk in chain.astream({"context": context, "query": q, "language": decision.language}):
            text = getattr(chunk, "content", None)
            if not text:
                continue

            text = _strip_urls(text)

            emit, carry = _normalize_stream_with_carry(text, carry=carry, max_carry=200)
            if not emit:
                continue

            full_answer += emit
            async for evt in emit_text(emit):
                yield evt

        # flush tail at end
        if carry:
            tail = normalize_stream_text(carry).strip()
            if tail:
                full_answer += tail
                async for evt in emit_text(tail):
                    yield evt


        meta = {
            "intent": "LEGAL",
            "language": decision.language,
            "confidence": decision.confidence,
            "chunks_retrieved": len(results),
            "context_chars": ctx_meta.get("final_context_chars", len(context)),
            "estimated_tokens": ctx_meta.get("estimated_tokens", 0),
            "query_time": round(time.time() - t0, 4),
            "cached": False,
        }
        yield sse({"type": "complete", "metadata": meta})

        cache_set_fn(cache_key, {"answer": full_answer, "sources": sources, "metadata": meta})
