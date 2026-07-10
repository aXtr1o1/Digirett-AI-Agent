import json
import logging
import re
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings

logger = logging.getLogger(__name__)


class DocumentClassifierAgent:

    _SYSTEM_PROMPT = """You are a legal query classifier. A user has uploaded a document AND asked a legal question.

Your job: decide HOW to answer the question.

OUTPUT — respond with ONLY valid JSON, no markdown fences:
{"intent": "<DOCQA|LEGAL|HYBRID|FOLLOWUP>", "reason": "<one short sentence>"}

CLASSIFICATION RULES:

DOCQA — use ONLY when:
  - The question wants answer that can ONLY be found in the document (e.g. "What does this document say about X?")
  - The question asks to summarize, explain, or extract content from the uploaded document
  - The question is about specific details that can ONLY exist inside a particular document 

LEGAL — use ONLY when:
  - The question asks about Norwegian law, statutes, regulations, legal principles
  - The document is only relevant as background context, NOT as the source of the answer
  - The question would be answerable even without the document

HYBRID — use when:
  - The question needs both what's IN the document AND what the law says
  - Both the document content AND legal statutes are necessary to answer correctly

FOLLOWUP — use when:
  - The question refers to a PREVIOUS answer in the conversation
  - The question continues a thread that was already answered (legal or doc-based)
  - The question has no new legal or document subject — it just extends the prior turn

IMPORTANT:
  - If in doubt between HYBRID and DOCQA, choose HYBRID
  - If in doubt between HYBRID and LEGAL, choose HYBRID
  - NEVER return CASUAL — that is handled upstream
  - Always return valid JSON only"""

    def __init__(self) -> None:
        self._llm = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=0.0,
        )
        logger.info("[OK] DocumentClassifierAgent initialized")

    async def classify(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        doc_summary: Optional[str] = None,
    ) -> Dict[str, str]:
        logger.debug(f"DocumentClassifierAgent: classifying '{query[:80]}'")

        # Build user content — include doc preview and recent history as context
        parts = []

        if doc_summary:
            parts.append(
                f"DOCUMENT PREVIEW (first 500 chars):\n{doc_summary[:500]}"
            )

        if conversation_history:
            recent = conversation_history[-4:]  # last 2 turns
            history_str = "\n".join(
                f"{m['role'].capitalize()}: {m['content'][:200]}"
                for m in recent
            )
            parts.append(f"RECENT CONVERSATION:\n{history_str}")

        parts.append(f"CURRENT QUERY:\n{query}")

        user_content = "\n\n".join(parts)

        try:
            messages = [
                SystemMessage(content=self._SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ]
            response = await self._llm.agenerate([messages])
            raw = response.generations[0][0].text.strip()

            # Strip markdown fences if present
            raw = re.sub(r"```json\s*", "", raw)
            raw = re.sub(r"```\s*", "", raw).strip()

            match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
            if match:
                result = json.loads(match.group(0))
                intent = result.get("intent", "HYBRID").upper()
                reason = result.get("reason", "")

                # Validate intent value
                if intent not in ("DOCQA", "LEGAL", "HYBRID", "FOLLOWUP"):
                    logger.warning(
                        f"[DEV:WARN] DocumentClassifierAgent: unknown intent '{intent}' — "
                        "defaulting to HYBRID"
                    )
                    intent = "HYBRID"

                logger.debug(
                    f"DocumentClassifierAgent: intent={intent} | reason='{reason}'"
                )
                return {"intent": intent, "reason": reason}

        except Exception as exc:
            logger.warning(
                f"[WARN] DocumentClassifierAgent failed, defaulting to HYBRID | {exc}"
            )

        return {"intent": "HYBRID", "reason": "Classification fallback"}