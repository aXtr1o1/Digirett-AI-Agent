import logging
import json
from typing import AsyncIterator, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings

logger = logging.getLogger(__name__)


class GeneratorAgent:
    

    CASUAL_SYSTEM_PROMPT = """You are a friendly, helpful AI assistant.

Your personality:
- Warm and conversational
- Natural and human-like
- Match the user's language (Norwegian ↔ English)
- Keep responses brief and friendly
- Use emojis sparingly (1-2 per message if appropriate)

Response style:
- For greetings: Greet back warmly and ask how you can help
- For emotional support: Be empathetic and kind
- For general help: Be friendly and offer assistance

IMPORTANT RULES:
- NEVER disclose internal model details or company behind the AI
- NO formal legal language unless asked
- Be natural and human
- Match their energy and tone
- Keep it conversational"""

    LEGAL_SYSTEM_PROMPT = """You are a professional AI Legal Assistant specialized in Norwegian law from Lovdata.

CRITICAL RULES:
1. ONLY use information from the provided KILDER (sources) below
2. NEVER use your general knowledge about Norwegian law
3. NEVER invent, assume, or hallucinate legal information
4. If sources don't contain the answer, say so clearly
5. If another country law, say clear and soft refusion .

RESPONSE STRUCTURE:
- Respond in **plain readable text**, not JSON.
- If a RESPONSE STYLE INSTRUCTION is present in the user message, follow it EXACTLY and ignore the default structure below.
- Otherwise, use the default structure with these ### subheadings in the language of the user's query:
  1. ### Legal Basis       (Norwegian: Hjemmel)
  2. ### Assessment        (Norwegian: Vurdering)
  3. ### Practical Steps   (Norwegian: Praktiske steg)
  4. ### Reservations      (Norwegian: Forbehold)
  5. ### Conclusion        (Norwegian: Konklusjon)
- Use **only one language** for the subheadings, matching the user's query language.
- Ensure each section summarizes the relevant information clearly, in plain text.


OUTPUT FORMAT:
{
  "answer": {
    "Regnskap og bokføringsplikt": "...",
    "Skattebetaling": "...",
    "Arbeidstakeres rettigheter": "...",
    "Konsekvenser av brudd": "...",
    "Regulerende lover": "..."
  },
  "score": 0.0
}

Then on the very last line append EXACTLY:
[SCORE:0.9]
(Replace 0.9 with actual score 0.0-1.0 based on how well sources answer the query)

SCORING GUIDE:
- 0.9-1.0: Sources fully and directly answer the query
- 0.5-0.8: Sources partially answer or are somewhat relevant
- 0.1-0.4: Sources are vague, barely relevant, or off-topic

LANGUAGE RULE:
- Always respond in the SAME language as the user's question
- English question → English answer (even if sources are Norwegian)
- Norwegian question → Norwegian answer"""

    def __init__(self, temperature: float = 0.7) -> None:
        self._default_temperature = temperature
        logger.info(" GeneratorAgent initialized")

    def _make_llm(self, temperature: float, streaming: bool = True) -> AzureChatOpenAI:
        return AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=temperature,
            streaming=streaming,
        )

    async def stream_casual(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        logger.info(" GeneratorAgent: casual stream starting")

        messages = [SystemMessage(content=self.CASUAL_SYSTEM_PROMPT)]

        if conversation_history:
            for msg in conversation_history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        messages.append(HumanMessage(content=query))

        llm = self._make_llm(temperature=temperature or self._default_temperature)

        async for chunk in llm.astream(messages):
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content

        logger.info(" GeneratorAgent: casual stream complete")

    async def stream_legal(
        self,
        query: str,
        rag_context: str,
        language: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        response_style: str = "",
    ) -> AsyncIterator[str]:
        import json
        logger.info(" GeneratorAgent: legal stream starting")

        buffer = ""  

        if not rag_context or not rag_context.strip():
            error_msg = (
                "Jeg finner ingen relevante juridiske utdrag fra min kunnskap."
                if language == "norwegian"
                else "I cannot find any relevant legal excerpts from My knowledge"
            )
            for char in error_msg:
                yield char
            yield "\n[SCORE:0.1]"
            return

        messages = [SystemMessage(content=self.LEGAL_SYSTEM_PROMPT)]

        if conversation_history:
            logger.info(
                f" GeneratorAgent: injecting {len(conversation_history)} history messages"
            )
            for msg in conversation_history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        # Prepend style instruction when the reasoning agent detected a user preference
        # e.g. "Brief overview requested. Keep under 150 words."
        style_block = f"RESPONSE STYLE INSTRUCTION:\n{response_style}\n\n" if response_style else ""

        user_prompt = (
            f"{style_block}"
            f"CRITICAL: Answer ONLY from the sources below.\n\n"
            f"KILDER (Sources):\n{rag_context}\n\n"
            f"SPØRSMÅL (Question):\n{query}\n\n"
            f"Respond in {language}. Be direct and cite sources.\n"
            f"Append [SCORE:x.x] on the very last line."
            f"Respond in **normal readable text**, not JSON. Keep it human-readable for the frontend."
        )
        messages.append(HumanMessage(content=user_prompt))

        llm = self._make_llm(temperature=temperature or 0.2)

        async for chunk in llm.astream(messages):
            if hasattr(chunk, "content") and chunk.content:
                buffer += chunk.content  # <-- append each chunk
                yield chunk.content     # <-- send chunk directly to frontend

        # No json parsing needed since frontend expects normal text
        logger.info(" GeneratorAgent: legal stream complete")