import json
import logging
import re
from typing import Dict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings

logger = logging.getLogger(__name__)


class IntentAgent:

    _SYSTEM_PROMPT =  """You are an intent and language classifier. 
Classify the user's query as either CASUAL or LEGAL.

Also, detect the DESIRED RESPONSE LANGUAGE:
- Usually, this is the language the user is writing in.
- HOWEVER, if the user explicitly asks for a response in a specific language (e.g., "explain in Norwegian", "summarize in English", "svar på norsk"), detect THAT language as the response language.

Constraints:
- If the current query refers to a previous legal topic (e.g., "explain it", "summarize", "more details"), classify it as LEGAL.
- Even if the query is written in ALL CAPITAL LETTERS, it must still be classified based on its meaning.

Output format:
{"intent": "LEGAL", "language": "norwegian"}"""

    def __init__(self) -> None:
        self._llm = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=0.1,
        )
        logger.info(" IntentAgent initialized")

    async def run(self, query: str) -> Dict[str, str]:
        
        logger.info(f" IntentAgent: classifying query '{query[:80]}'")

        try:
            messages = [
                SystemMessage(content=self._SYSTEM_PROMPT),
                HumanMessage(content=query),
            ]
            response = await self._llm.agenerate([messages])
            raw = response.generations[0][0].text.strip()

            # Strip markdown fences if present
            raw = re.sub(r"```json\s*", "", raw)
            raw = re.sub(r"```\s*", "", raw).strip()

            match = re.search(r"\{[^}]+\}", raw)
            if match:
                result = json.loads(match.group(0))
                intent = result.get("intent", "CASUAL").upper()
                language = result.get("language", "english").lower()
                logger.info(f" IntentAgent: intent={intent}, language={language}")
                return {"intent": intent, "language": language}

        except Exception as exc:
            logger.warning(f"  IntentAgent LLM failed, defaulting to CASUAL | {exc}")

        # Fallback
        return {"intent": "CASUAL", "language": "english"}