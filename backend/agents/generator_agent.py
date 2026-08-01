import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings
from prompts.generator_prompts import CASUAL_SYSTEM_PROMPT, LEGAL_SYSTEM_PROMPT
from utils.history_formatter import convert_history_to_messages

logger = logging.getLogger(__name__)

# ── NAMED CONSTANTS & TEMPERATURE CONFIGURATIONS ──────────────────────
CASUAL_TEMPERATURE = 0.7
LEGAL_TEMPERATURE = 0.2
PRE_STREAM_MAX_RETRIES = 2
PRE_STREAM_RETRY_DELAY = 0.5


class LanguageInstructionBuilder:
    """Builder class for language instructions without inline string mutation."""

    @staticmethod
    def build(language: Optional[str]) -> str:
        if not language:
            return ""
        lang_name = language.capitalize()
        return (
            f"\n\nCRITICAL LANGUAGE INSTRUCTION:\n"
            f"You MUST respond ONLY in {lang_name}. Do NOT use Norwegian unless {lang_name} is Norwegian.\n"
            f"Even though the legal sources (KILDER) are in Norwegian, you must write your entire explanation, analysis, and response in {lang_name}."
        )


class GeneratorAgent:

    def __init__(self, llm: Optional[Any] = None, temperature: float = CASUAL_TEMPERATURE) -> None:
        self._default_temperature = temperature
        if llm is not None:
            self._streaming_llm = llm
        else:
            self._streaming_llm = AzureChatOpenAI(
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
                temperature=self._default_temperature,
                streaming=True,
            )
        self._casual_system_prompt = CASUAL_SYSTEM_PROMPT
        self._legal_system_prompt = LEGAL_SYSTEM_PROMPT
        logger.info("[OK] GeneratorAgent initialized")

    def _convert_history_to_messages(
        self, conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> List[BaseMessage]:
        """Delegates to shared history_formatter utility."""
        return convert_history_to_messages(conversation_history)

    async def _stream_llm_response(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        user_memory: str = "",
        log_label: str = "CASUAL",
    ) -> AsyncIterator[str]:
        """
        Shared streaming engine (DRY principle).
        Applies immutable prompt composition (System Prompt -> Memory Block -> User Query)
        and pre-stream connection retry strategy.
        """
        # Immutable Prompt Composition
        prompt_content = system_prompt
        if user_memory:
            prompt_content = f"{system_prompt}\n\n{user_memory}"

        messages: List[BaseMessage] = [SystemMessage(content=prompt_content)]
        messages.extend(self._convert_history_to_messages(conversation_history))
        messages.append(HumanMessage(content=user_prompt))

        # Pre-stream connection attempt with retry strategy
        first_chunk = None
        stream_gen = None

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
                if attempt < PRE_STREAM_MAX_RETRIES:
                    logger.warning(f" GeneratorAgent: [{log_label}] pre-stream attempt {attempt + 1} failed: {exc}. Retrying...")
                    await asyncio.sleep(PRE_STREAM_RETRY_DELAY * (2 ** attempt))
                else:
                    logger.error(f" GeneratorAgent: [{log_label}] pre-stream failed after retries: {exc}")
                    raise

        chunk_count = 0
        if first_chunk and hasattr(first_chunk, "content") and first_chunk.content:
            chunk_count += 1
            yield first_chunk.content

        if stream_gen:
            async for chunk in stream_gen:
                if hasattr(chunk, "content") and chunk.content:
                    chunk_count += 1
                    yield chunk.content

        logger.debug(f"GeneratorAgent: {log_label} stream complete | {chunk_count} chunks generated")

    async def stream_casual(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        language: Optional[str] = None,
        user_memory: str = "",
    ) -> AsyncIterator[str]:
        logger.debug("GeneratorAgent: casual stream starting")

        lang_instruction = LanguageInstructionBuilder.build(language)
        system_prompt = f"{self._casual_system_prompt}{lang_instruction}"

        async for chunk in self._stream_llm_response(
            system_prompt=system_prompt,
            user_prompt=query,
            conversation_history=conversation_history,
            user_memory=user_memory,
            log_label="CASUAL",
        ):
            yield chunk

    async def stream_legal(
        self,
        query: str,
        rag_context: str,
        language: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        response_style: str = "",
        user_memory: str = "",
    ) -> AsyncIterator[str]:
        logger.debug("GeneratorAgent: legal stream starting")

        if not rag_context or not rag_context.strip():
            error_msg = (
                "Jeg finner ingen relevante juridiske utdrag fra min kunnskap."
                if language == "norwegian"
                else "I cannot find any relevant legal excerpts from My knowledge"
            )
            # Yield single block instead of character-by-character loop
            yield error_msg
            yield "\n[SCORE:0.1]"
            return

        style_block = f"RESPONSE STYLE INSTRUCTION:\n{response_style}\n\n" if response_style else ""
        lang_name = language.capitalize() if language else "the requested language"

        user_prompt = (
            f"{style_block}"
            f"CRITICAL: Answer ONLY from the sources below.\n\n"
            f"KILDER (Sources):\n{rag_context}\n\n"
            f"SPØRSMÅL (Question):\n{query}\n\n"
            f"CRITICAL LANGUAGE INSTRUCTION: You MUST respond entirely in {lang_name} UNLESS the user explicitly requested a different language in their QUESTION.\n"
            f"Even though the sources (KILDER) are in Norwegian, you must write your entire explanation and analysis in {lang_name}.\n"
            f"Prepend [SCORE:x.x] on the very first line.\n"
            f"Respond in **normal readable text**, not JSON. Keep it human-readable for the frontend."
        )

        async for chunk in self._stream_llm_response(
            system_prompt=self._legal_system_prompt,
            user_prompt=user_prompt,
            conversation_history=conversation_history,
            user_memory=user_memory,
            log_label="LEGAL",
        ):
            yield chunk