import json
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

try:
    import json_repair
except ImportError:
    json_repair = None

from config import settings
from prompts.document_classifier_prompt import DOCUMENT_CLASSIFIER_PROMPT

logger = logging.getLogger(__name__)

# ── NAMED CONSTANTS ──────────────────────────────────────────────────
MAX_LOG_QUERY_LEN = 80
MAX_DOC_PREVIEW_LEN = 500
MAX_HISTORY_TURNS = 4
MAX_HISTORY_MSG_LEN = 200


class IntentEnum(str, Enum):
    DOCQA = "DOCQA"
    LEGAL = "LEGAL"
    HYBRID = "HYBRID"
    FOLLOWUP = "FOLLOWUP"


class ClassificationResult(BaseModel):
    intent: IntentEnum = Field(default=IntentEnum.HYBRID)
    reason: str = Field(default="")


class PromptBuilder:
    """Builder class for assembling document classification context."""

    def __init__(self) -> None:
        self._parts: List[str] = []

    def add_document(self, doc_summary: Optional[str]) -> "PromptBuilder":
        if doc_summary:
            preview = doc_summary[:MAX_DOC_PREVIEW_LEN]
            self._parts.append(f"DOCUMENT PREVIEW (first {MAX_DOC_PREVIEW_LEN} chars):\n{preview}")
        return self

    def add_history(self, conversation_history: Optional[List[Dict[str, str]]]) -> "PromptBuilder":
        if conversation_history:
            recent = conversation_history[-MAX_HISTORY_TURNS:]
            history_lines = []
            for m in recent:
                if isinstance(m, dict):
                    role = str(m.get("role", "user")).capitalize()
                    content = str(m.get("content", ""))[:MAX_HISTORY_MSG_LEN]
                    history_lines.append(f"{role}: {content}")
            if history_lines:
                self._parts.append("RECENT CONVERSATION:\n" + "\n".join(history_lines))
        return self

    def add_query(self, query: str) -> "PromptBuilder":
        self._parts.append(f"CURRENT QUERY:\n{query}")
        return self

    def build(self) -> str:
        return "\n\n".join(self._parts)


class DocumentClassifierAgent:

    def __init__(self, llm: Optional[Any] = None) -> None:
        """
        Accepts injected LLM client (Dependency Inversion Principle).
        If llm is None, falls back to default AzureChatOpenAI instance.
        """
        if llm is not None:
            self._llm = llm
        else:
            self._llm = AzureChatOpenAI(
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
                temperature=0.0,
            )
        self._system_prompt = DOCUMENT_CLASSIFIER_PROMPT
        logger.info("[OK] DocumentClassifierAgent initialized")

    async def classify(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        doc_summary: Optional[str] = None,
    ) -> Dict[str, str]:
        logger.debug(f"DocumentClassifierAgent: classifying query (len={len(query)})")

        # Assemble prompt using PromptBuilder
        builder = PromptBuilder()
        user_content = (
            builder
            .add_document(doc_summary)
            .add_history(conversation_history)
            .add_query(query)
            .build()
        )

        try:
            messages = [
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=user_content),
            ]
            response = await self._llm.agenerate([messages])
            raw = response.generations[0][0].text.strip()

            # Clean markdown code blocks if present
            raw = re.sub(r"```json\s*", "", raw)
            raw = re.sub(r"```\s*", "", raw).strip()

            # Parse JSON with json_repair / json.loads fallback
            parsed_data = None
            try:
                parsed_data = json.loads(raw)
            except Exception:
                if json_repair is not None:
                    try:
                        parsed_data = json_repair.loads(raw)
                    except Exception:
                        pass
                if not isinstance(parsed_data, dict):
                    match = re.search(r"\{.*?\}", raw, re.DOTALL)
                    if match:
                        try:
                            parsed_data = json.loads(match.group(0))
                        except Exception:
                            pass


            if isinstance(parsed_data, dict):
                # Normalize raw intent string
                raw_intent = str(parsed_data.get("intent", "HYBRID")).upper()
                if raw_intent not in ("DOCQA", "LEGAL", "HYBRID", "FOLLOWUP"):
                    logger.warning(f"[DEV:WARN] DocumentClassifierAgent: unknown intent '{raw_intent}' — defaulting to HYBRID")
                    raw_intent = "HYBRID"

                raw_reason = parsed_data.get("reason", "")
                if isinstance(raw_reason, dict):
                    raw_reason = str(raw_reason.get("text", raw_reason))

                validated = ClassificationResult(
                    intent=IntentEnum(raw_intent),
                    reason=str(raw_reason),
                )

                logger.debug(f"DocumentClassifierAgent: intent={validated.intent.value} | reason='{validated.reason}'")
                return {"intent": validated.intent.value, "reason": validated.reason}

        except Exception as exc:
            logger.warning(f"[WARN] DocumentClassifierAgent failed, defaulting to HYBRID | {exc}")

        return {"intent": "HYBRID", "reason": "Classification fallback"}