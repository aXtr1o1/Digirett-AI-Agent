import logging
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from agents.generator_agent import GeneratorAgent
from agents.intent_agent import IntentAgent
from config import settings
from telemetry.tracing import llm_span

logger = logging.getLogger(__name__)


def _extract_score(full_text: str):
    
    pattern = re.compile(r"\[SCORE:\s*([0-9.]+)\]")
    match = pattern.search(full_text)

    if match:
        score = min(max(float(match.group(1)), 0.0), 1.0)
        answer = pattern.sub("", full_text).rstrip("\n").strip()
    else:
        logger.warning("  No [SCORE:x.x] found in legal response, defaulting to 0.5")
        score = 0.5
        answer = full_text.strip()

    return answer, score


def _score_to_confidence(score: float) -> str:
    if score >= 0.9:
        return "Fully supported by sources"
    elif score >= 0.5:
        return "Partially supported by sources"
    else:
        return "Weakly supported or not found in sources"


class LLMService:
    

    def __init__(self, temperature: float = 0.7) -> None:
        try:
            # Shared LLM instance (used for check_connection and title generation)
            self._llm = AzureChatOpenAI(
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
                temperature=temperature,
            )
            self._intent_agent = IntentAgent()
            self._generator_agent = GeneratorAgent(temperature=temperature)

            logger.info(
                f" LLMService initialized | deployment={settings.AZURE_OPENAI_DEPLOYMENT}"
            )
        except Exception as exc:
            logger.error(f" LLMService init failed | {exc}", exc_info=True)
            raise

    # ── Factory methods (used by RAGService to wire OrchestratorAgent) ──

    def get_intent_agent(self) -> IntentAgent:
        return self._intent_agent

    def get_generator_agent(self) -> GeneratorAgent:
        return self._generator_agent

    # ── Public generation methods ─────────────────────────────────────────

    async def generate_casual_stream(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        language: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Stream casual response tokens. No RAG context involved."""
        async with llm_span("casual_generation"):
            async for token in self._generator_agent.stream_casual(
                query=query,
                conversation_history=conversation_history,
                temperature=temperature,
                language=language,
            ):
                yield token

    async def generate_legal_answer(
        self,
        query: str,
        rag_context: str,
        language: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        response_style: str = "",
    ) -> Dict[str, Any]:
       
        if not rag_context or not rag_context.strip():
            error_msg = (
                "Jeg finner ingen relevante juridiske utdrag fra min kunnskap."
                if language == "norwegian"
                else "I cannot find any relevant legal excerpts from My Knowledge."
            )
            return {
                "answer": error_msg,
                "score": 0.1,
                "confidence": "No sources available",
                "tokens_used": 0,
            }

        full_text = ""
        async with llm_span("legal_answer_scoring"):
            async for token in self._generator_agent.stream_legal(
                query=query,
                rag_context=rag_context,
                language=language,
                conversation_history=conversation_history,
                temperature=temperature,
                response_style=response_style,
            ):
                full_text += token

        answer, score = _extract_score(full_text)
        confidence = _score_to_confidence(score)

        logger.info(f" Legal answer scored | score={score} | confidence={confidence}")
        return {
            "answer": answer,
            "score": score,
            "confidence": confidence,
            "tokens_used": 0,   # token counting requires an extra API call; skipped for latency
        }

    async def generate_legal_stream(
        self,
        query: str,
        rag_context: str,
        language: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        response_style: str = "",
    ) -> AsyncIterator[str]:
        
        if not rag_context or not rag_context.strip():
            error_msg = (
                "Jeg finner ingen relevante juridiske utdrag fra min kunnskap.."
                if language == "norwegian"
                else "I cannot find any relevant legal excerpts from my knowledge."
            )
            yield "__SCORE__0.1__"
            for char in error_msg:
                yield char
            return

        score_re = re.compile(r"\[SCORE:\s*([0-9.]+)\]")
        buffer = ""
        score_emitted = False

        async with llm_span("legal_stream"):
            async for token in self._generator_agent.stream_legal(
                query=query,
                rag_context=rag_context,
                language=language,
                conversation_history=conversation_history,
                temperature=temperature,
                response_style=response_style,
            ):
                if not score_emitted:
                    buffer += token
                    match = score_re.search(buffer)
                    if match:
                        score_val = float(match.group(1))
                        yield f"__SCORE__{score_val}__"
                        score_emitted = True
                        
                        clean = score_re.sub("", buffer).lstrip()
                        if clean:
                            yield clean
                        buffer = ""
                    elif len(buffer) > 25 and "[" not in buffer:
                        # Model missed the tag at the start! Default to 0.5
                        yield "__SCORE__0.5__"
                        score_emitted = True
                        yield buffer
                        buffer = ""
                else:
                    yield token

            if not score_emitted:
                # Fallback if stream ended and no score found
                yield "__SCORE__0.5__"
                if buffer:
                    yield buffer

        logger.info(" Legal stream complete")

    async def generate_conversation_title(
        self,
        first_user_message: str,
        first_assistant_message: str,
        second_user_message: str,
        second_assistant_message: str,
    ) -> str:

        
        prompt = (
            "Generate a very short, descriptive title (max 5 words, no quotes) "
            "based on the following conversation:\n\n"

            f"User: {first_user_message[:300]}\n"
            f"Assistant: {first_assistant_message[:300]}\n\n"

            f"User: {second_user_message[:300]}\n"
            f"Assistant: {second_assistant_message[:300]}\n\n"

            "Rules:\n"
            "- Maximum 5 words\n"
            "- No quotes\n"
            "- No punctuation\n"
            "- No explanations\n"
            "- Return ONLY the title\n"
        )

        try:
            async with llm_span("title_generation"):
                messages = [HumanMessage(content=prompt)]
                response = await self._llm.agenerate([messages])
                title = response.generations[0][0].text.strip().strip('"').strip("'")
                logger.info(f" Generated conversation title: '{title}'")
                return title[:100]  # hard cap at 100 chars
        except Exception as exc:
            logger.warning(f"  Title generation failed, using fallback | {exc}")
            return first_user_message[:60]

    async def generate_conversation_summary(
        self,
        messages: List[Dict[str, str]],
    ) -> str:
        """
        Generate a concise summary of the last N messages.
        Called by MemoryAgent.maybe_update_summary every 10 messages.
        """
        convo_text = "\n".join(
            f"{m['role'].capitalize()}: {m['content'][:300]}"
            for m in messages
        )
        prompt = (
            "Summarize the following conversation excerpt in 3-5 sentences. "
            "Focus on the key legal topics discussed, questions asked, and conclusions reached. "
            "Be concise and factual.\n\n"
            f"{convo_text}\n\n"
            "Summary:"
        )
        try:
            async with llm_span("summary_generation"):
                response = await self._llm.agenerate([[HumanMessage(content=prompt)]])
                summary = response.generations[0][0].text.strip()
                logger.info(f"✅ Conversation summary generated ({len(summary)} chars)")
                return summary
        except Exception as exc:
            logger.warning(f"⚠️ generate_conversation_summary failed | {exc}")
            # Fallback: join message snippets
            return " | ".join(
                f"{m['role']}: {m['content'][:80]}" for m in messages[:4]
            )

    async def check_connection(self) -> bool:
        """Smoke-test the Azure OpenAI endpoint. Returns True when reachable."""
        try:
            await self._llm.agenerate([[HumanMessage(content="ping")]])
            return True
        except Exception as exc:
            logger.error(f" LLM connection check failed | {exc}")
            return False
    async def summarize_document_stream(
        self,
        doc_text: str,
    ) -> AsyncIterator[str]:
        """
        Stream a concise document summary in the document's own language.
        Bypasses GeneratorAgent — uses the raw LLM with a neutral system prompt.
        """
        truncated = doc_text[:60_000]

        messages = [
            SystemMessage(content=(
                "You are a document summarizer. "
                "Identify the language of the document and Strictly respond ONLY in that language. "
                "English document → English summary. "
                "Norwegian document → Norwegian summary. "
                "Never translate. Never switch languages. and Never mix languages in your response."
            )),
            HumanMessage(content=(
                f"Summarize the following document in 3-5 sentences. "
                f"Cover only the main purpose and key points. "
                f"Do not use code blocks or backticks.\n\n"
                f"DOCUMENT:\n{truncated}"
            )),
        ]

        llm = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=0.3,
            streaming=True,
        )

        async with llm_span("document_summarization"):
            async for chunk in llm.astream(messages):
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content