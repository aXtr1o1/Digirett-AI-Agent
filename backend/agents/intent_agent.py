import asyncio
import logging
from typing import Any, Dict, Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

from config import settings
from prompts.intent_prompts import INTENT_SYSTEM_PROMPT
from utils.json_response_parser import parse_json_response

logger = logging.getLogger(__name__)

# ── NAMED CONSTANTS ──────────────────────────────────────────────────
MAX_LOG_QUERY_LEN = 80
DEFAULT_INTENT = "CASUAL"
DEFAULT_LANGUAGE = "english"
INTENT_TEMPERATURE = 0.1
MAX_RETRIES = 2
RETRY_DELAY = 0.5


class IntentResult(BaseModel):
    intent: Literal["CASUAL", "LEGAL"] = Field(default=DEFAULT_INTENT)
    language: Literal["english", "norwegian"] = Field(default=DEFAULT_LANGUAGE)


class IntentAgent:

    def __init__(self, llm: Optional[Any] = None) -> None:
        if llm is not None:
            self._llm = llm
        else:
            self._llm = AzureChatOpenAI(
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
                temperature=INTENT_TEMPERATURE,
            )
        self._system_prompt = INTENT_SYSTEM_PROMPT
        logger.info("[OK] IntentAgent initialized")

    async def run(self, query: str) -> Dict[str, str]:
        logger.info(f"IntentAgent: classifying query '{query[:MAX_LOG_QUERY_LEN]}'")

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=query),
        ]

        # Retry strategy with exponential backoff on 429/500/503 errors
        response = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._llm.agenerate([messages])
                break
            except Exception as exc:
                if attempt < MAX_RETRIES:
                    logger.warning(f" IntentAgent: attempt {attempt + 1} failed: {exc}. Retrying...")
                    await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                else:
                    logger.error(f" IntentAgent: LLM execution failed after retries: {exc}")

        if response and response.generations and response.generations[0]:
            raw_text = response.generations[0][0].text.strip()
            
            # Centralized JSON response parser (Explicit regex removal)
            parsed_data = parse_json_response(raw_text)
            
            if parsed_data:
                raw_intent = str(parsed_data.get("intent", DEFAULT_INTENT)).upper()
                raw_lang = str(parsed_data.get("language", DEFAULT_LANGUAGE)).lower()

                if raw_intent not in ("CASUAL", "LEGAL"):
                    raw_intent = DEFAULT_INTENT
                if raw_lang not in ("english", "norwegian"):
                    raw_lang = DEFAULT_LANGUAGE

                validated = IntentResult(
                    intent=raw_intent,
                    language=raw_lang,
                )

                logger.info(f"IntentAgent: intent={validated.intent}, language={validated.language}")
                return {"intent": validated.intent, "language": validated.language}

        logger.warning("IntentAgent: returning default fallback classification")
        return {"intent": DEFAULT_INTENT, "language": DEFAULT_LANGUAGE}