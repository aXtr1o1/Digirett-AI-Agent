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

def _safe_int(val: Any, default: int) -> int:
    return val if isinstance(val, int) else default

# MAX_LOG_QUERY_LEN: Truncates user query in log lines to 80 chars to prevent PII leakage and log bloat.
MAX_LOG_QUERY_LEN = min(_safe_int(getattr(settings, "INTENT_LOG_QUERY_LEN", 80), 80), 200)

# DEFAULT_INTENT / DEFAULT_LANGUAGE: Fallback values if LLM JSON parsing completely fails or encounters a timeout.
DEFAULT_INTENT = "CASUAL"
DEFAULT_LANGUAGE = "english"

# INTENT_TEMPERATURE: Low temperature (0.1) forces deterministic, high-precision classification results.
INTENT_TEMPERATURE = 0.1

# MAX_RETRIES / RETRY_DELAY: Fast pre-execution retries for transient 429/503 Azure OpenAI errors with a sane max cap of 5 retries.
MAX_RETRIES = min(_safe_int(getattr(settings, "INTENT_MAX_RETRIES", 2), 2), 5)
RETRY_DELAY = getattr(settings, "INTENT_RETRY_DELAY", 0.5) if isinstance(getattr(settings, "INTENT_RETRY_DELAY", 0.5), (int, float)) else 0.5



class IntentResult(BaseModel):
    intent: Literal["CASUAL", "LEGAL"] = Field(default=DEFAULT_INTENT)
    language: Literal["english", "norwegian"] = Field(default=DEFAULT_LANGUAGE)


class IntentAgent:

    def __init__(self, llm: Optional[Any] = None) -> None:
        if llm is not None:
            self._llm = llm
        else:
            try:
                if not getattr(settings, "AZURE_OPENAI_ENDPOINT", None) or not getattr(settings, "AZURE_OPENAI_API_KEY", None):
                    raise ValueError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be configured in environment/settings.")

                self._llm = AzureChatOpenAI(
                    azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                    api_key=settings.AZURE_OPENAI_API_KEY,
                    api_version=settings.AZURE_OPENAI_API_VERSION,
                    deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
                    temperature=INTENT_TEMPERATURE,
                )
            except Exception as exc:
                logger.error(f" IntentAgent init failed — AzureChatOpenAI client creation error | {exc}")
                raise RuntimeError(f"IntentAgent initialization failed due to Azure OpenAI client error: {exc}") from exc

        self._system_prompt = INTENT_SYSTEM_PROMPT
        logger.info("[OK] IntentAgent initialized")

    async def run(self, query: str) -> Dict[str, str]:
        logger.info(f"IntentAgent: classifying query '{query[:MAX_LOG_QUERY_LEN]}'")

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=query),
        ]

        def _is_transient_error(exc: Exception) -> bool:
            err_str = str(exc).lower()
            transient_keywords = ["429", "500", "502", "503", "504", "rate limit", "timeout", "connection"]
            return any(kw in err_str for kw in transient_keywords)

        # Retry strategy with exponential backoff on transient errors only (429/5xx/timeouts)
        response = None
        last_exception: Optional[Exception] = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._llm.agenerate([messages])
                break
            except Exception as exc:
                last_exception = exc
                is_transient = _is_transient_error(exc)
                backoff_delay = min(RETRY_DELAY * (2 ** attempt), 2.0)

                if is_transient and attempt < MAX_RETRIES:
                    logger.warning(
                        f"⚠️ IntentAgent: transient attempt failed | "
                        f"attempt={attempt + 1}/{MAX_RETRIES + 1} | "
                        f"backoff_ms={int(backoff_delay * 1000)} | error={exc}"
                    )
                    await asyncio.sleep(backoff_delay)
                else:
                    if not is_transient:
                        logger.error(f" IntentAgent: non-transient error encountered — failing without retry | error={exc}")
                    else:
                        logger.error(
                            f" IntentAgent: LLM execution exhausted all retries | "
                            f"total_attempts={MAX_RETRIES + 1} | final_error={exc}"
                        )
                    break

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
