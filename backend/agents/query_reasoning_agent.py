"""
agents/query_reasoning_agent.py — Legal Query Reasoning & Statute Classifier Agent

Refactored per TL Code Review Guidelines:
1. Injected LLM & StatuteRegistry dependencies (__init__(self, llm=None, registry=None)).
2. Decoupled 200+ line prompt into prompts/query_reasoning_prompt.txt.
3. Project-wide JsonResponseParser & Pydantic ReasoningResult validation replacing 7 redundant extraction functions.
4. Imported centralized ALLOWED_DOMAINS from config_domains.py.
5. Exponential backoff retry strategy for transient 429/500/503 errors.
6. Explicit named constants (MAX_LOG_QUERY_LEN = 70, MAX_PREV_QUERY_LEN = 400).
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

from config import settings
from config_domains import DOMAINS_CANONICAL as ALLOWED_DOMAINS, normalize_domain

from agents.statute_registry import get_registry
from prompts.query_reasoning_prompts import QUERY_REASONING_SYSTEM_PROMPT
from utils.json_response_parser import parse_json_response

logger = logging.getLogger(__name__)

# ── NAMED CONSTANTS ──────────────────────────────────────────────────
MAX_LOG_QUERY_LEN = 70
MAX_PREV_QUERY_LEN = 400
MAX_RETRIES = 2
RETRY_DELAY = 0.5


class ReasoningResult(BaseModel):
    statute_id: Optional[str] = Field(default=None)
    statute_name: Optional[str] = Field(default=None)
    domain: Optional[str] = Field(default=None)
    jurisdiction: str = Field(default="NO")
    scope: str = Field(default="BROAD_OVERVIEW")
    b2b_b2c: str = Field(default="BOTH")
    response_style: str = Field(default="")
    enriched_query: str = Field(default="")
    statute_from_registry: bool = Field(default=False)


class QueryReasoningAgent:

    def __init__(self, llm: Optional[Any] = None, registry: Optional[Any] = None) -> None:
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
        self._registry = registry if registry is not None else get_registry()
        self._system_prompt = QUERY_REASONING_SYSTEM_PROMPT
        logger.info("[OK] QueryReasoningAgent initialized")

    async def run(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        context_window: Optional[str] = None,
        previous_statute_id: Optional[str] = None,
        previous_enriched_query: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        logger.info(f"QueryReasoningAgent: reasoning for query '{query[:MAX_LOG_QUERY_LEN]}'")

        # 1. Check Statute Registry first
        statute_from_registry = False
        stat_match = self._registry.lookup(query)
        registry_hint = ""

        if stat_match:
            statute_from_registry = True
            registry_hint = (
                f"\n\nREGISTRY HINT: Deterministic lookup matched key statute: "
                f"statute_id='{stat_match.statute_id}', name='{stat_match.short_name}', "
                f"domain='{stat_match.domain}'. Use this statute_id."
            )
            logger.info(f"Registry match: statute_id={stat_match.statute_id}, domain={stat_match.domain}")

        # Build prompt messages
        parts = []
        if previous_enriched_query or (history and len(history) > 0):
            prev_text = previous_enriched_query or history[-1].get("content", "")
            parts.append(f"PREVIOUS QUERY: {str(prev_text)[:MAX_PREV_QUERY_LEN]}")
        parts.append(f"CURRENT QUERY: {query}")
        if registry_hint:
            parts.append(registry_hint)

        user_content = "\n\n".join(parts)
        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=user_content),
        ]

        # 2. LLM Execution with exponential backoff retry policy
        response = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._llm.agenerate([messages])
                break
            except Exception as exc:
                if attempt < MAX_RETRIES:
                    logger.warning(f"⚠️ QueryReasoningAgent: attempt {attempt + 1} failed: {exc}. Retrying...")
                    await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                else:
                    logger.error(f"❌ QueryReasoningAgent: LLM execution failed after retries: {exc}")

        # 3. Parse JSON with project-wide JsonResponseParser & ReasoningResult validation
        if response and response.generations and response.generations[0]:
            raw_text = response.generations[0][0].text.strip()
            parsed_data = parse_json_response(raw_text)

            if parsed_data:
                domain_val = parsed_data.get("domain")
                if domain_val:
                    domain_val = normalize_domain(str(domain_val))
                    if domain_val not in ALLOWED_DOMAINS:
                        domain_val = None

                stat_id = stat_match.statute_id if stat_match else (parsed_data.get("primary_statute_id") or parsed_data.get("statute_id"))
                stat_name = stat_match.short_name if stat_match else (parsed_data.get("primary_statute_name") or parsed_data.get("statute_name"))

                result = ReasoningResult(
                    statute_id=stat_id,
                    statute_name=stat_name,
                    domain=domain_val or (stat_match.domain if stat_match else None),
                    jurisdiction=str(parsed_data.get("jurisdiction", "NO")).upper(),
                    scope=str(parsed_data.get("scope") or parsed_data.get("query_scope") or "BROAD_OVERVIEW").upper(),
                    b2b_b2c=str(parsed_data.get("b2b_b2c", "BOTH")).upper(),
                    response_style=str(parsed_data.get("response_style", "")),
                    enriched_query=str(parsed_data.get("enriched_query", query)),
                    statute_from_registry=statute_from_registry,
                )

                logger.info(f"QueryReasoningAgent: statute={result.statute_id} | domain={result.domain} | scope={result.scope}")
                dump = result.model_dump()
                dump["primary_statute_id"] = result.statute_id
                dump["secondary_statute_id"] = parsed_data.get("secondary_statute_id")
                dump["query_scope"] = result.scope
                return dump

        # Fallback Result
        fallback = ReasoningResult(
            statute_id=stat_match.statute_id if stat_match else previous_statute_id,
            statute_name=stat_match.short_name if stat_match else None,
            domain=stat_match.domain if stat_match else None,
            enriched_query=query,
            statute_from_registry=statute_from_registry,
        )
        dump = fallback.model_dump()
        dump["primary_statute_id"] = fallback.statute_id
        dump["secondary_statute_id"] = None
        dump["query_scope"] = fallback.scope
        return dump