import logging
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from agents.memory_agent import MemoryAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.retriever_agent import RetrieverAgent
from agents.query_reasoning_agent import QueryReasoningAgent
from agents.router_agent import RouterAgent
from agents.document_classifier_agent import DocumentClassifierAgent
from agents.document_qa_agent import DocumentQAAgent
# from agents.source_validation_agent import SourceValidationAgent  # TEMPORARILY DISABLED
from db.milvus_client import MilvusClient
from db.redis_client import RedisClient
from db.supabase_client import SupabaseClient
from services.embedding_service import EmbeddingService
from services.llm_service import LLMService, _extract_score, _score_to_confidence
from services.document_service import DocumentService
from config import settings
from config_domains import normalize_domain

logger = logging.getLogger(__name__)

# Redis key template for storing reasoning context between turns
_REASONING_META_KEY = "reasoning:statute:{conversation_id}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Statute ID → Lovdata URL resolver  (unchanged from Phase 1)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_LOVDATA_BASE = "https://lovdata.no"

_TYPE_PREFIX_MAP = {
    "LOV": "lov",
    "FOR": "forskrift",
    "RES": "forskrift",
}


def _resolve_statute_url(statute_id: Optional[str]) -> Optional[str]:
    if not statute_id:
        return None

    value = statute_id.strip()

    if value.startswith("https://lovdata.no"):
        value = value.replace("/dokument/NL/lov/", "/lov/")
        value = value.replace("/dokument/SF/forskrift/", "/forskrift/")
        value = value.replace("/dokument/lov/", "/lov/")
        value = value.replace("/dokument/forskrift/", "/forskrift/")
        return value

    type_path = "lov"
    prefix_match = re.match(r"^([A-Z]+)-(.+)$", value, re.IGNORECASE)
    if prefix_match:
        prefix = prefix_match.group(1).upper()
        type_path = _TYPE_PREFIX_MAP.get(prefix, "lov")
        value = prefix_match.group(2)

    parts = value.split("-")
    if len(parts) != 4:
        logger.warning(
            f"⚠️  _resolve_statute_url: cannot parse '{statute_id}' — skipping filter"
        )
        return None

    year, month, day, number = parts
    if not all(p.isdigit() for p in parts):
        logger.warning(
            f"⚠️  _resolve_statute_url: non-numeric parts in '{statute_id}' — skipping filter"
        )
        return None

    url = f"{_LOVDATA_BASE}/{type_path}/{year}-{month}-{day}-{int(number)}"
    logger.debug(f"🗂  statute_id '{statute_id}' → URL '{url}'")
    return url


def _is_statute_explicit(query: str) -> bool:
    """
    Detect if user explicitly named a law in the query.

    Returns True if query contains patterns like:
    - "Lov om..."
    - "LOV-"
    - "bestemmelse i"
    - "§" (section symbol)

    Returns False if statute is inferred from mechanism/domain.
    """
    if not query:
        return False

    query_lower = query.lower()
    explicit_patterns = [
        "lov om",
        "loven",
        "loven om",
        "loven for",
        "loven 20",  # LOV-YYYY format
        "lov-",
        "for-",  # FOR = forskrift
        "res-",  # RES = resolution
        "bestemmelse i",
        "kapittel",
        "§",
        "lovdatas",
        "lovdata",
    ]

    return any(pattern in query_lower for pattern in explicit_patterns)


class RAGService:

    def __init__(
        self,
        llm_service: LLMService,
        milvus_client: MilvusClient,
        redis_client: RedisClient,
        supabase_client: SupabaseClient,
        embedding_service: EmbeddingService,
        document_service: Optional[DocumentService] = None,
    ) -> None:
        self._llm = llm_service
        self._milvus = milvus_client
        self._redis = redis_client
        self._supabase = supabase_client
        self._embedding = embedding_service
        self._document_service = document_service

        self._memory_agent = MemoryAgent(
            redis_client=redis_client,
            supabase_client=supabase_client,
        )
        self._retriever_agent = RetrieverAgent(
            embedding_service=embedding_service,
            milvus_client=milvus_client,
        )
        self._orchestrator = OrchestratorAgent(
            intent_agent=llm_service.get_intent_agent(),
            memory_agent=self._memory_agent,
            generator_agent=llm_service.get_generator_agent(),
        )
        self._reasoning_agent = QueryReasoningAgent()
        self._router_agent = RouterAgent()
        self._doc_classifier = DocumentClassifierAgent()
        self._doc_qa_agent = DocumentQAAgent()
        # self._validation_agent = SourceValidationAgent()  # TEMPORARILY DISABLED

        logger.info(
            "✅ RAGService initialized | "
            "retrieval=v3 (4-level fallback + BM25) | document agent active"
        )

    async def process_query(
        self,
        query: str,
        conversation_id: str,
        user_role: str = "user",
        top_k: int = 50,
        min_score: float = 0.0,
    ) -> AsyncIterator[Dict[str, Any]]:

        try:
            logger.info(f"🤖 RAGService: processing query '{query[:60]}'")

            # ── Session turn limit check ───────────────────────────────────
            if self._document_service:
                turn_allowed, turns_remaining = self._document_service.check_turn_limit(
                    conversation_id
                )
                if not turn_allowed:
                    limit_msg = (
                        "Du har nådd grensen på 10 samtaler per økt (4 timer). "
                        "Økten din tilbakestilles automatisk etter 4 timer fra start."
                        "  |  "
                        "You have reached the 10-conversation limit per session (4 hours). "
                        "Your session resets automatically after 4 hours."
                    )
                    logger.warning("⛔ Session turn limit exceeded")
                    yield {
                        "type": "intent",
                        "data": {"intent": "BLOCKED", "language": "unknown"},
                    }
                    for char in limit_msg:
                        yield {"type": "token", "data": char}
                    yield {
                        "type": "complete",
                        "metadata": {
                            "intent": "BLOCKED",
                            "language": "unknown",
                            "full_answer": limit_msg,
                            "score": 0.0,
                            "confidence": "Session turn limit reached",
                            "rag_chunks": [],
                            "tokens_generated": 0,
                        },
                    }
                    return

                self._document_service.increment_turn_count(conversation_id)
                logger.info(
                    f"🔢 Turn {10 - turns_remaining + 1}/10 | conv={conversation_id}"
                )

            # ── Load history ───────────────────────────────────────────────
            history = self._orchestrator.load_history(
                conversation_id=conversation_id,
                limit=10,
            )

            # ── Classify intent ────────────────────────────────────────────
            logger.info("🎯 Classifying query intent...")
            intent_result = await self._orchestrator.classify(
                query=query,
                conversation_id=conversation_id,
            )
            intent = intent_result["intent"]
            language = intent_result["language"]
            logger.info(f"🎯 Intent: {intent} | Language: {language}")

            yield {"type": "intent", "data": {"intent": intent, "language": language}}

            if intent == "LEGAL":
                # ── Document routing ───────────────────────────────────────
                if (
                    self._document_service
                    and self._document_service.has_documents(conversation_id)
                ):
                    logger.info(
                        "📄 Document detected in session - routing decision needed"
                    )
                    doc_summary = self._document_service.get_doc_summary(
                        conversation_id
                    )
                    doc_class_result = await self._doc_classifier.classify(
                        query=query,
                        conversation_history=history,
                        doc_summary=doc_summary,
                    )
                    doc_intent = doc_class_result["intent"]
                    logger.info(
                        f"📄 Document intent: {doc_intent} | "
                        f"reason='{doc_class_result.get('reason', '')}'"
                    )

                    if doc_intent == "DOCQA":
                        logger.info("↳ Route: DOCQA (Document Only)")
                        async for event in self._handle_docqa(
                            query=query,
                            language=language,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event

                    elif doc_intent == "HYBRID":
                        logger.info("↳ Route: HYBRID (Document + VDB)")
                        async for event in self._handle_hybrid(
                            query=query,
                            language=language,
                            top_k=top_k,
                            min_score=min_score,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event

                    elif doc_intent == "FOLLOWUP":
                        logger.info("↳ Route: FOLLOWUP")
                        async for event in self._handle_followup_with_doc(
                            query=query,
                            language=language,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event

                    else:
                        logger.info("↳ Route: LEGAL (No Document)")
                        async for event in self._handle_legal(
                            query=query,
                            language=language,
                            top_k=top_k,
                            min_score=min_score,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event
                else:
                    logger.info("📋 No document in session - standard VDB search")
                    async for event in self._handle_legal(
                        query=query,
                        language=language,
                        top_k=top_k,
                        min_score=min_score,
                        history=history,
                        conversation_id=conversation_id,
                        user_role=user_role,
                    ):
                        yield event
            else:
                if (
                    self._document_service
                    and self._document_service.has_documents(conversation_id)
                ):
                    logger.info(
                        "📄 CASUAL query but document in session — "
                        "routing through doc classifier"
                    )
                    doc_summary = self._document_service.get_doc_summary(
                        conversation_id
                    )
                    doc_class_result = await self._doc_classifier.classify(
                        query=query,
                        conversation_history=history,
                        doc_summary=doc_summary,
                    )
                    doc_intent = doc_class_result["intent"]
                    logger.info(
                        f"📄 Doc classifier (from CASUAL): {doc_intent} | "
                        f"reason='{doc_class_result.get('reason', '')}'"
                    )

                    if doc_intent == "DOCQA":
                        async for event in self._handle_docqa(
                            query=query,
                            language=language,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event
                    elif doc_intent == "HYBRID":
                        async for event in self._handle_hybrid(
                            query=query,
                            language=language,
                            top_k=top_k,
                            min_score=min_score,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event
                    elif doc_intent == "FOLLOWUP":
                        async for event in self._handle_followup_with_doc(
                            query=query,
                            language=language,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event
                    else:
                        # doc_intent == "LEGAL" or truly unrelated — casual is fine
                        logger.info("💬 CASUAL query (doc present but unrelated)")
                        async for event in self._handle_casual(query, history, language):
                            yield event
                else:
                    logger.info("💬 CASUAL query")
                    async for event in self._handle_casual(query, history, language):
                        yield event

        except Exception as exc:
            logger.error(
                f"❌ RAGService.process_query failed | query='{query[:50]}' | {exc}",
                exc_info=True,
            )
            yield {"type": "error", "message": str(exc)}

    async def _handle_casual(
        self,
        query: str,
        history: List[Dict[str, str]],
        language: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("💬 CASUAL pipeline")

        yield {"type": "sources", "data": []}

        full_answer = ""
        token_count = 0

        async for token in self._llm.generate_casual_stream(
            query=query,
            conversation_history=history,
        ):
            token_count += 1
            full_answer += token
            yield {"type": "token", "data": token}

        yield {
            "type": "complete",
            "metadata": {
                "intent": "CASUAL",
                "language": language,
                "tokens_generated": token_count,
                "score": 1.0,
                "confidence": "Casual conversation",
                "full_answer": full_answer,
                "rag_chunks": [],
            },
        }
        logger.info(f"✅ CASUAL pipeline complete | tokens={token_count}")

    async def _handle_legal(
        self,
        query: str,
        language: str,
        top_k: int,
        min_score: float,
        history: List[Dict[str, str]],
        conversation_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("⚖️  LEGAL pipeline (v6 — registry-aware + section_ref sources)")
 
        context_window = history[-9:] if history else []
 
        # ── Load previous reasoning context from Redis ─────────────────────
        previous_statute_id = None
        previous_enriched_query = None
        try:
            redis_key = _REASONING_META_KEY.format(conversation_id=conversation_id)
            reasoning_meta = self._redis.get_conversation_meta(redis_key)
            if reasoning_meta:
                previous_statute_id = reasoning_meta.get("statute_id")
                previous_enriched_query = reasoning_meta.get("enriched_query")
                logger.info(
                    f"📖 Loaded reasoning context | "
                    f"statute_id={previous_statute_id} | "
                    f"prev_query=\'{str(previous_enriched_query)[:60]}\'"
                )
        except Exception as exc:
            logger.warning(f"⚠️  Could not read reasoning meta from Redis | {exc}")
 
        # ── [1] QueryReasoningAgent ────────────────────────────────────────
        reasoning_result = await self._reasoning_agent.run(
            query=query,
            context_window=context_window,
            previous_statute_id=previous_statute_id,
            previous_enriched_query=previous_enriched_query,
        )
        enriched_query        = reasoning_result["enriched_query"]
        primary_statute_id    = reasoning_result.get("primary_statute_id")
        response_style        = reasoning_result.get("response_style", "")
        domain                = reasoning_result.get("domain")
        jurisdiction          = reasoning_result.get("jurisdiction")
        statute_from_registry = reasoning_result.get("statute_from_registry", False)
 
        if domain:
            domain = normalize_domain(domain) or domain
 
        logger.info(f"🧠 Enriched query : \'{enriched_query[:80]}\'")
        logger.info(
            f"   statute={primary_statute_id} | "
            f"registry={statute_from_registry} | "
            f"domain={domain} | jurisdiction={jurisdiction} | style=\'{response_style}\'"
        )
 
        # ── [2] RouterAgent ────────────────────────────────────────────────
        router_result = await self._router_agent.run(
            raw_query=query,
            enriched_query=enriched_query,
            domain_hint=domain,
        )
        final_domain          = domain or router_result.get("domain") or None
        final_jurisdiction    = jurisdiction or router_result.get("jurisdiction") or None
        subdomain_candidates  = router_result.get("subdomain_candidates") or []
        b2b_b2c               = router_result.get("b2b_b2c") or "BOTH"
 
        if final_domain:
            final_domain = normalize_domain(final_domain) or final_domain
 
        logger.info(
            f"🔀 Router: domain={final_domain} | subdomains={subdomain_candidates} | "
            f"b2b_b2c={b2b_b2c} | jurisdiction={final_jurisdiction} | "
            f"confidence={router_result.get('confidence')}"
        )
 
        # ── Persist reasoning context ──────────────────────────────────────
        try:
            redis_key = _REASONING_META_KEY.format(conversation_id=conversation_id)
            self._redis.set_conversation_meta(
                redis_key,
                {"statute_id": primary_statute_id, "enriched_query": enriched_query},
                ttl=1800,
            )
        except Exception as exc:
            logger.warning(f"⚠️  Could not save reasoning meta to Redis | {exc}")
 
        # ── [3] Resolve statute → Lovdata URL ─────────────────────────────
        statute_filter = _resolve_statute_url(primary_statute_id)
        logger.info(f"🗂  statute_filter: \'{primary_statute_id}\' → \'{statute_filter}\'")
 
        # ── [4] RetrieverAgent (5-level fallback + BM25) ──────────────────
        search_results = await self._retriever_agent.run(
            query=query,
            enriched_query=enriched_query,
            top_k=top_k,
            min_score=min_score,
            history=history,
            statute_filter=statute_filter,
            domain=final_domain,
            jurisdiction=final_jurisdiction,
            subdomain_candidates=subdomain_candidates,
            b2b_b2c=b2b_b2c,
            statute_from_registry=statute_from_registry,
            user_role=user_role,
        )
 
        # ── [5] Handle empty retrieval ─────────────────────────────────────
        if not search_results:
            logger.warning(
                f"⚠️  No results after 5-level fallback | "
                f"statute={primary_statute_id} | domain={final_domain}"
            )
            yield {"type": "sources", "data": []}
            no_result = (
                "Jeg finner ingen relevante lovutdrag i den tilgjengelige "
                "Lovdata-databasen som direkte svarer på dette spørsmålet."
                if language == "norwegian"
                else
                "I cannot find any relevant legal excerpts for this question."
            )
            for char in no_result:
                yield {"type": "token", "data": char}
            yield {
                "type": "complete",
                "metadata": {
                    "intent": "LEGAL",
                    "language": language,
                    "primary_statute_id": primary_statute_id,
                    "chunks_retrieved": 0,
                    "score": 0.1,
                    "confidence": "No sources found",
                    "full_answer": no_result,
                    "rag_chunks": [],
                },
            }
            return
 
        # ── [6] Build RAG context ──────────────────────────────────────────
        rag_context = self._build_context(search_results)
        if len(rag_context) > settings.CONTEXT_MAX_LENGTH:
            rag_context = rag_context[:settings.CONTEXT_MAX_LENGTH]
            logger.warning(f"⚠️  RAG context truncated to {settings.CONTEXT_MAX_LENGTH} chars")
 
        # ── [7] Score gate — score the answer before streaming ────────────
        # generate_legal_answer() calls the LLM once (non-streaming) to get
        # the score. If score < 0.5, the chunks do not support the query —
        # block the answer so the user never sees hallucinated legal content.
        score_result = await self._llm.generate_legal_answer(
            query=query,
            rag_context=rag_context,
            language=language,
            conversation_history=history,
            response_style=response_style,
        )
        score       = score_result["score"]
        confidence  = score_result["confidence"]
        scored_answer = score_result["answer"]
 
        logger.info(
            f"📊 Score={score} | Confidence={confidence} | chunks={len(search_results)}"
        )
 
        if score < 0.5:
            logger.warning(
                f"⚠️  Score={score} < 0.5 — blocking answer | "
                f"statute={primary_statute_id}"
            )
            yield {"type": "sources", "data": []}
            no_support = (
                "Jeg finner ingen relevante juridiske utdrag fra min kunnskap."
                if language == "norwegian"
                else "I cannot find any relevant legal excerpts from my knowledge."
            )
            for char in no_support:
                yield {"type": "token", "data": char}
            yield {
                "type": "complete",
                "metadata": {
                    "intent": "LEGAL",
                    "language": language,
                    "primary_statute_id": primary_statute_id,
                    "chunks_retrieved": len(search_results),
                    "tokens_generated": len(no_support),
                    "score": score,
                    "confidence": confidence,
                    "full_answer": no_support,
                    "rag_chunks": [],
                },
            }
            return
 
        # ── [8] Emit sources (score ≥ 0.5 only) with section_ref ──────────
        # Build URLs with section anchor so frontend shows exact paragraph links
        seen_urls: set = set()
        visible_sources: List[str] = []
        for chunk in search_results:
            base_url    = chunk.get("source_doc_url") or chunk.get("url") or ""
            section_ref = (chunk.get("section_ref") or "").strip()
            # Full URL with section anchor: "https://lovdata.no/.../lov/YYYY-MM-DD-N/§6-1"
            full_url = f"{base_url}/{section_ref}" if section_ref else base_url
            if full_url and full_url not in seen_urls:
                seen_urls.add(full_url)
                visible_sources.append(full_url)
            # Also emit base URL so frontend shows the law itself
            if base_url and base_url not in seen_urls:
                seen_urls.add(base_url)
                visible_sources.append(base_url)
 
        yield {"type": "sources", "data": visible_sources}
        logger.info(f"✅ Emitted {len(visible_sources)} source URLs (section_ref included)")
 
        # ── [9] Stream answer ─────────────────────────────────────────────
        full_answer = ""
        token_count = 0
 
        async for token in self._llm.generate_legal_stream(
            query=query,
            rag_context=rag_context,
            language=language,
            conversation_history=history,
            response_style=response_style,
        ):
            token_count += 1
            full_answer += token
            yield {"type": "token", "data": token}
 
        yield {
            "type": "complete",
            "metadata": {
                "intent": "LEGAL",
                "language": language,
                "primary_statute_id": primary_statute_id,
                "chunks_retrieved": len(search_results),
                "tokens_generated": token_count,
                "score": score,
                "confidence": confidence,
                "full_answer": scored_answer,
                "rag_chunks": search_results,
            },
        }
        logger.info(
            f"✅ LEGAL pipeline complete | "
            f"chunks={len(search_results)} | tokens={token_count} | score={score} | "
            f"fallback=L{search_results[0].get('fallback_level', 0) if search_results else 'n/a'}"
        )

    async def _handle_docqa(
        self,
        query: str,
        language: str,
        history: List[Dict[str, str]],
        conversation_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("📄 DOCQA pipeline")

        doc_text = self._document_service.get_all_session_document_texts(
            conversation_id
        )

        if not doc_text:
            no_doc_msg = (
                "Ingen dokumenter er lastet opp i denne økten."
                if language == "norwegian"
                else "No documents have been uploaded in this session."
            )
            yield {"type": "sources", "data": []}
            for char in no_doc_msg:
                yield {"type": "token", "data": char}
            yield {
                "type": "complete",
                "metadata": {
                    "intent": "DOCQA",
                    "language": language,
                    "full_answer": no_doc_msg,
                    "score": 0.0,
                    "confidence": "No document",
                    "rag_chunks": [],
                    "tokens_generated": 0,
                },
            }
            return

        yield {"type": "sources", "data": []}

        full_answer = ""
        token_count = 0

        async for token in self._doc_qa_agent.stream_docqa(
            query=query,
            doc_text=doc_text,
            language=language,
            conversation_history=history,
        ):
            token_count += 1
            full_answer += token
            yield {"type": "token", "data": token}

        # Strip [SCORE:x.x] from docqa answer
        score_pattern = re.compile(r"\[SCORE:([0-9.]+)\]")
        score_match = score_pattern.search(full_answer)
        score = float(score_match.group(1)) if score_match else 0.7
        clean_answer = score_pattern.sub("", full_answer).strip()

        yield {
            "type": "complete",
            "metadata": {
                "intent": "DOCQA",
                "language": language,
                "tokens_generated": token_count,
                "score": score,
                "confidence": _score_to_confidence(score),
                "full_answer": clean_answer,
                "rag_chunks": [],
            },
        }
        logger.info(
            f"✅ DOCQA pipeline complete | tokens={token_count} | score={score}"
        )

    async def _handle_hybrid(
        self,
        query: str,
        language: str,
        top_k: int,
        min_score: float,
        history: List[Dict[str, str]],
        conversation_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("🔀 HYBRID pipeline (Document + VDB)")

        doc_text = self._document_service.get_all_session_document_texts(
            conversation_id
        )
        if not doc_text:
            logger.warning("⚠️  HYBRID: No document text — falling back to LEGAL")
            async for event in self._handle_legal(
                query=query,
                language=language,
                top_k=top_k,
                min_score=min_score,
                history=history,
                conversation_id=conversation_id,
                user_role=user_role,
            ):
                yield event
            return
        search_results = await self._retriever_agent.run(
            query=query,
            enriched_query=query,
            top_k=top_k,
            min_score=min_score,
            history=history,
            statute_filter=None,
            domain=None,
            jurisdiction=None,
            subdomain_candidates=[],
            b2b_b2c="BOTH",
            statute_from_registry=False,
            user_role=user_role,
        )

        rag_context = self._build_context(search_results) if search_results else ""

        yield {"type": "sources", "data": []}

        full_answer = ""
        token_count = 0

        async for token in self._doc_qa_agent.stream_hybrid(
            query=query,
            doc_text=doc_text,
            rag_context=rag_context,
            language=language,
            conversation_history=history,
        ):
            token_count += 1
            full_answer += token
            yield {"type": "token", "data": token}

        score_pattern = re.compile(r"\[SCORE:([0-9.]+)\]")
        score_match = score_pattern.search(full_answer)
        score = float(score_match.group(1)) if score_match else 0.7
        clean_answer = score_pattern.sub("", full_answer).strip()

        yield {
            "type": "complete",
            "metadata": {
                "intent": "HYBRID",
                "language": language,
                "tokens_generated": token_count,
                "score": score,
                "confidence": _score_to_confidence(score),
                "full_answer": clean_answer,
                "rag_chunks": search_results,
            },
        }
        logger.info(
            f"✅ HYBRID pipeline complete | tokens={token_count} | score={score}"
        )

    async def _handle_followup_with_doc(
        self,
        query: str,
        language: str,
        history: List[Dict[str, str]],
        conversation_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("🔁 FOLLOWUP pipeline (context-aware, doc session)")

        # Re-use the last assistant answer as context via DOCQA
        async for event in self._handle_docqa(
            query=query,
            language=language,
            history=history,
            conversation_id=conversation_id,
        ):
            # Re-label intent so chat.py saves it correctly
            if event.get("type") == "complete":
                meta = event.get("metadata", {})
                meta["intent"] = "FOLLOWUP"
                yield {"type": "complete", "metadata": meta}
            else:
                yield event

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONTEXT BUILDER — section_ref used for human-readable citation anchor
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _build_context(chunks: List[Dict[str, Any]]) -> str:
        """
        Build the RAG context string passed to the generator.

        Uses:
          - section_ref  → human-readable citation anchor (e.g. "§ 6-1")
          - source_doc_url → full Lovdata URL for attribution header
          - text         → chunk content
        """
        parts = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk.get("text", "").strip()
            if not text:
                continue

            section_ref = chunk.get("section_ref") or ""
            source_url = chunk.get("source_doc_url") or chunk.get("url") or ""
            domain = chunk.get("domain") or ""
            subdomain = chunk.get("subdomain") or ""

            header_parts = []
            if source_url:
                header_parts.append(source_url)
            if section_ref:
                header_parts.append(section_ref)
            if domain:
                header_parts.append(domain)
            if subdomain:
                header_parts.append(subdomain)

            header = " | ".join(header_parts) if header_parts else f"Source {i}"
            parts.append(f"[{i}] {header}\n{text}")

        return "\n\n---\n\n".join(parts)

    async def _extract_document_summary(self, doc_text: str) -> str:
        doc_excerpt = doc_text[:2000]
        try:
            summary_prompt = (
                f"Summarize the following text in 2-3 sentences, "
                f"focusing on key topics and domains:\n\n{doc_excerpt}\n\n"
                f"Summary (max 100 words):"
            )
            summary = ""
            async for token in self._llm.generate_casual_stream(
                query=summary_prompt,
                conversation_history=[],
            ):
                summary += token
            return summary.strip()[:settings.ENRICHMENT_SUMMARY_MAX_CHARS]
        except Exception as exc:
            logger.warning(f"⚠️  Summary extraction failed | {exc}")
            return doc_text[:500]