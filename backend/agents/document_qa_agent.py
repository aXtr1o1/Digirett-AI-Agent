import asyncio
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings
from prompts.document_qa_prompts import DOCQA_SYSTEM_PROMPT, HYBRID_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

def _safe_int(val: Any, default: int) -> int:
    return val if isinstance(val, int) else default

# Max character limits loaded from settings with sane upper caps (max 100,000 chars)
MAX_DOC_CHARS_DOCQA = min(_safe_int(getattr(settings, "DOCQA_MAX_DOC_CHARS", 60_000), 60_000), 100_000)
MAX_DOC_CHARS_HYBRID = min(_safe_int(getattr(settings, "HYBRID_MAX_DOC_CHARS", 40_000), 40_000), 80_000)
MAX_HISTORY_TURNS = 6
PRE_STREAM_MAX_RETRIES = 2
PRE_STREAM_RETRY_DELAY = 0.5




class PromptBuilder:
    """Builder class for assembling DocumentQAAgent user prompts."""

    def __init__(self) -> None:
        self._parts: List[str] = []

    def document(self, doc_text: str, max_chars: int = 60_000) -> "PromptBuilder":
        truncated_doc = doc_text[:max_chars]
        if len(doc_text) > max_chars:
            truncated_doc += "\n\n[... document truncated for length ...]"
        self._parts.append(f"DOCUMENT TEXT:\n{truncated_doc}")
        return self

    def rag(self, rag_context: Optional[str]) -> "PromptBuilder":
        cleaned_rag = (rag_context or "").strip()
        if cleaned_rag:
            self._parts.append(f"---\n\nLEGAL SOURCES (from Lovdata):\n{cleaned_rag}")
        return self


    def question(self, query: str) -> "PromptBuilder":
        self._parts.append(f"---\n\nQUESTION: {query}")
        return self

    def language(self, lang: Optional[str], is_hybrid: bool = False) -> "PromptBuilder":
        DEFAULT_LANG = "NORWEGIAN"
        ALLOWED_LANGUAGES = {"NORWEGIAN", "ENGLISH", "NO", "EN"}

        if not lang or not isinstance(lang, str) or not lang.strip():
            logger.warning(f" PromptBuilder: language is empty or invalid ('{lang}') — defaulting to '{DEFAULT_LANG}'")
            target_lang = DEFAULT_LANG
        else:
            cleaned_lang = lang.strip().upper()
            if cleaned_lang in ALLOWED_LANGUAGES:
                target_lang = cleaned_lang
            else:
                logger.info(f" PromptBuilder: unmapped language '{lang}' — passing through as '{cleaned_lang}'")
                target_lang = cleaned_lang

        extra = "Cross-reference both sources.\n" if is_hybrid else ""
        self._parts.append(
            f"CRITICAL: You MUST respond entirely in {target_lang} UNLESS the user explicitly requested a different language in their QUESTION.\n"
            f"Even if the sources are in another language, your response MUST be in {target_lang}.\n"
            f"{extra}"
            "Append [SCORE:x.x] on the very last line."
        )
        return self


    def build(self) -> str:
        return "\n\n".join(self._parts)


def _parse_response_score(text: str) -> float:
    """
    Extracts [SCORE:x.x] score from model response, validates range 0.0 - 1.0,
    and logs inconsistencies.
    """
    if not text:
        return 0.5
    match = re.search(r"\[SCORE:\s*([0-9.]+)\]", text)
    if match:
        try:
            score = float(match.group(1))
            if 0.0 <= score <= 1.0:
                return score
            logger.warning(f" [SCORE:x.x] out of range [0.0, 1.0]: {score} — defaulting to 0.5")
        except ValueError:
            logger.warning(f" Failed to parse score value from match: {match.group(1)}")
    else:
        logger.debug(" Response omitted [SCORE:x.x] tag — defaulting to 0.5")
    return 0.5


class DocumentQAAgent:

    def __init__(self, llm: Optional[Any] = None, temperature: float = 0.2) -> None:
        self._temperature = temperature
        if llm is not None:
            self._streaming_llm = llm
        else:
            self._streaming_llm = AzureChatOpenAI(
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
                temperature=self._temperature,
                streaming=True,
            )
        self._docqa_system_prompt = DOCQA_SYSTEM_PROMPT
        self._hybrid_system_prompt = HYBRID_SYSTEM_PROMPT
        logger.info("[OK] DocumentQAAgent initialized")

    def _build_history_messages(
        self, conversation_history: Optional[List[Dict[str, str]]]
    ) -> List[BaseMessage]:
        """Maps conversation history dicts to LangChain Message objects with robust type guards."""
        messages: List[BaseMessage] = []
        if conversation_history and isinstance(conversation_history, list):
            recent = conversation_history[-MAX_HISTORY_TURNS:]
            for msg in recent:
                if not isinstance(msg, dict):
                    continue
                role = str(msg.get("role", "")).lower().strip()
                content = str(msg.get("content", "")).strip()
                if not content:
                    continue

                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))
        return messages

    async def _stream_response(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        log_label: str = "DOCQA",
    ) -> AsyncIterator[str]:
        """
        Shared streaming method (DRY principle).
        Applies pre-stream retry strategy during connection phase, then streams chunks cleanly.
        """
        messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]
        messages.extend(self._build_history_messages(conversation_history))
        messages.append(HumanMessage(content=user_prompt))

        # Pre-stream connection attempt with retry strategy (fetches initial generator)
        first_chunk = None
        stream_gen = None

        last_exception: Optional[Exception] = None
        for attempt in range(PRE_STREAM_MAX_RETRIES + 1):
            try:
                gen = self._streaming_llm.astream(messages)
                first_chunk = await gen.__anext__()
                stream_gen = gen
                break
            except StopAsyncIteration:
                stream_gen = None
                break
            except Exception as exc:
                last_exception = exc
                backoff_delay = min(PRE_STREAM_RETRY_DELAY * (2 ** attempt), 2.0)
                if attempt < PRE_STREAM_MAX_RETRIES:
                    logger.warning(
                        f" [{log_label}] Pre-stream connection attempt failed | "
                        f"attempt={attempt + 1}/{PRE_STREAM_MAX_RETRIES + 1} | "
                        f"backoff_ms={int(backoff_delay * 1000)} | error={exc}"
                    )
                    await asyncio.sleep(backoff_delay)
                else:
                    logger.error(
                        f" [{log_label}] Pre-stream connection exhausted all retries | "
                        f"total_attempts={PRE_STREAM_MAX_RETRIES + 1} | final_error={exc}"
                    )
                    raise RuntimeError(
                        f"DocumentQAAgent [{log_label}] connection failed after {PRE_STREAM_MAX_RETRIES + 1} attempts. "
                        f"Last error: {exc}"
                    ) from exc

        chunk_count = 0
        try:
            if first_chunk and hasattr(first_chunk, "content") and first_chunk.content:
                chunk_count += 1
                yield first_chunk.content

            if stream_gen:
                async for chunk in stream_gen:
                    if hasattr(chunk, "content") and chunk.content:
                        chunk_count += 1
                        yield chunk.content
        except GeneratorExit:
            logger.debug(f"[{log_label}] Client disconnected — closing LLM stream generator")
            raise
        except Exception as exc:
            logger.error(f" [{log_label}] LLM streaming error: {exc}")
            raise
        finally:
            if stream_gen and hasattr(stream_gen, "aclose"):
                try:
                    await stream_gen.aclose()
                except Exception as close_exc:
                    logger.debug(f"[{log_label}] Non-fatal error closing stream generator: {close_exc}")
            logger.debug(f"DocumentQAAgent: {log_label} stream finalized | {chunk_count} chunks emitted")


    async def stream_docqa(
        self,
        query: str,
        doc_text: str,
        language: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        logger.debug("DocumentQAAgent: DOCQA stream starting (document only)")

        user_prompt = (
            PromptBuilder()
            .document(doc_text, max_chars=MAX_DOC_CHARS_DOCQA)
            .question(query)
            .language(language, is_hybrid=False)
            .build()
        )

        async for chunk in self._stream_response(
            system_prompt=self._docqa_system_prompt,
            user_prompt=user_prompt,
            conversation_history=conversation_history,
            log_label="DOCQA",
        ):
            yield chunk

    async def stream_hybrid(
        self,
        query: str,
        doc_text: str,
        rag_context: Optional[str],
        language: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        logger.debug("DocumentQAAgent: HYBRID stream starting (document + VDB)")

        cleaned_rag = (rag_context or "").strip()
        if not cleaned_rag:
            logger.warning(" DocumentQAAgent: HYBRID stream requested but RAG context is empty or None")

        user_prompt = (
            PromptBuilder()
            .document(doc_text, max_chars=MAX_DOC_CHARS_HYBRID)
            .rag(cleaned_rag)
            .question(query)
            .language(language, is_hybrid=True)
            .build()
        )


        async for chunk in self._stream_response(
            system_prompt=self._hybrid_system_prompt,
            user_prompt=user_prompt,
            conversation_history=conversation_history,
            log_label="HYBRID",
        ):
            yield chunk