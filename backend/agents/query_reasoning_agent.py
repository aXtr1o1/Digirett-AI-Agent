import asyncio
import logging
import re
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


def _safe_int(val: Any, default: int) -> int:
    return val if isinstance(val, int) else default


# Configurable constants loaded from settings with sane upper caps
MAX_LOG_QUERY_LEN = min(
    _safe_int(getattr(settings, "QUERY_REASONING_MAX_LOG_LEN", 70), 70), 200
)
MAX_PREV_QUERY_LEN = min(
    _safe_int(getattr(settings, "QUERY_REASONING_MAX_PREV_LEN", 400), 400), 1000
)
MAX_RETRIES = min(
    _safe_int(getattr(settings, "QUERY_REASONING_MAX_RETRIES", 2), 2), 5
)
RETRY_DELAY = (
    getattr(settings, "QUERY_REASONING_RETRY_DELAY", 0.5)
    if isinstance(getattr(settings, "QUERY_REASONING_RETRY_DELAY", 0.5), (int, float))
    else 0.5
)

_VALID_SCOPES = frozenset({"BROAD_OVERVIEW", "SPECIFIC_DOCUMENT", "SPECIFIC_PROVISION"})
_VALID_B2B_B2C = frozenset({"B2B", "B2C", "BOTH"})


class ReasoningResult(BaseModel):
    statute_id: Optional[str] = Field(default=None)
    statute_name: Optional[str] = Field(default=None)
    domain: Optional[str] = Field(default=None)
    jurisdiction: str = Field(default="NO")
    scope: str = Field(default="BROAD_OVERVIEW")
    b2b_b2c: str = Field(default="BOTH")
    response_style: str = Field(default="")
    corrected_query: Optional[str] = Field(default=None)
    enriched_query: str = Field(default="")
    statute_from_registry: bool = Field(default=False)
    registry_target_match: bool = Field(default=False)


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
        context_window: Optional[Any] = None,
        previous_statute_id: Optional[str] = None,
        previous_enriched_query: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        logger.info(
            "QueryReasoningAgent: reasoning for query '%s'",
            query[:MAX_LOG_QUERY_LEN],
        )

        # 1. Precision-first deterministic statute registry lookup.
        statute_from_registry = False
        stat_match = self._registry.lookup(query)
        registry_hint = ""

        if stat_match:
            statute_from_registry = True
            registry_hint = (
                "\n\nREGISTRY HINT: Deterministic lookup matched a named legal document: "
                f"statute_id='{stat_match.statute_id}', "
                f"name='{getattr(stat_match, 'matched_alias', None) or stat_match.short_name}', "
                f"document_type='{getattr(stat_match, 'document_type', 'UNKNOWN')}', "
                f"domain='{stat_match.domain}'. "
                "Use this statute_id unless the current query clearly refers to a different document."
            )
            logger.info(
                "Registry match: statute_id=%s, name=%s, domain=%s",
                stat_match.statute_id,
                getattr(stat_match, "matched_alias", None) or stat_match.short_name,
                stat_match.domain,
            )

        # Build prompt messages. Preserve previous-query behavior exactly.
        parts: List[str] = []
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

        # 2. LLM execution with existing exponential-backoff policy.
        response = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._llm.agenerate([messages])
                break
            except Exception as exc:
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "QueryReasoningAgent: attempt %s failed: %s. Retrying...",
                        attempt + 1,
                        exc,
                    )
                    await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                else:
                    logger.error(
                        "QueryReasoningAgent: LLM execution failed after retries: %s",
                        exc,
                    )

        # 3. Parse and validate model output.
        if response and response.generations and response.generations[0]:
            raw_text = response.generations[0][0].text.strip()
            parsed_data = parse_json_response(raw_text)

            if parsed_data:
                domain_val = parsed_data.get("domain")
                if domain_val:
                    domain_val = normalize_domain(str(domain_val))
                    if domain_val not in ALLOWED_DOMAINS:
                        domain_val = None

                stat_id = (
                    stat_match.statute_id
                    if stat_match
                    else (
                        parsed_data.get("primary_statute_id")
                        or parsed_data.get("statute_id")
                    )
                )
                stat_name = (
                    stat_match.short_name
                    if stat_match
                    else (
                        parsed_data.get("primary_statute_name")
                        or parsed_data.get("statute_name")
                    )
                )

                corrected_q = str(parsed_data.get("corrected_query") or query)
                parsed_scope = self._normalize_scope(
                    parsed_data.get("scope") or parsed_data.get("query_scope")
                )
                final_scope = self._resolve_scope(
                    query=corrected_q,
                    stat_match=stat_match,
                    parsed_scope=parsed_scope,
                )

                result = ReasoningResult(
                    statute_id=stat_id,
                    statute_name=stat_name,
                    domain=domain_val or (stat_match.domain if stat_match else None),
                    jurisdiction=self._normalize_jurisdiction(
                        parsed_data.get("jurisdiction", "NO")
                    ),
                    scope=final_scope,
                    b2b_b2c=self._normalize_b2b_b2c(
                        parsed_data.get("b2b_b2c", "BOTH")
                    ),
                    response_style=str(parsed_data.get("response_style", "")),
                    corrected_query=corrected_q,
                    enriched_query=str(
                        parsed_data.get("enriched_query", corrected_q)
                    ),
                    statute_from_registry=statute_from_registry,
                    registry_target_match=self._registry_match_is_target(
                        corrected_q, stat_match
                    ),
                )

                logger.info(
                    "QueryReasoningAgent: statute=%s | domain=%s | scope=%s",
                    result.statute_id,
                    result.domain,
                    result.scope,
                )
                if corrected_q != query:
                    logger.info(
                        "QueryReasoningAgent: spell-corrected query | original='%s' | corrected='%s'",
                        query[:60],
                        corrected_q[:60],
                    )

                dump = result.model_dump()
                dump["primary_statute_id"] = result.statute_id
                dump["secondary_statute_id"] = parsed_data.get("secondary_statute_id")
                dump["query_scope"] = result.scope
                dump["corrected_query"] = result.corrected_query or query
                return dump

        # Fallback result keeps existing behavior but still applies deterministic
        # scope detection for an explicitly matched regulation/document.
        fallback_scope = self._resolve_scope(
            query=query,
            stat_match=stat_match,
            parsed_scope="BROAD_OVERVIEW",
        )
        fallback = ReasoningResult(
            statute_id=stat_match.statute_id if stat_match else previous_statute_id,
            statute_name=stat_match.short_name if stat_match else None,
            domain=stat_match.domain if stat_match else None,
            scope=fallback_scope,
            corrected_query=query,
            enriched_query=query,
            statute_from_registry=statute_from_registry,
            registry_target_match=self._registry_match_is_target(query, stat_match),
        )
        dump = fallback.model_dump()
        dump["primary_statute_id"] = fallback.statute_id
        dump["secondary_statute_id"] = None
        dump["query_scope"] = fallback.scope
        return dump

    @staticmethod
    def _normalize_scope(value: Any) -> str:
        scope = str(value or "BROAD_OVERVIEW").strip().upper()
        return scope if scope in _VALID_SCOPES else "BROAD_OVERVIEW"

    @staticmethod
    def _normalize_b2b_b2c(value: Any) -> str:
        normalized = str(value or "BOTH").strip().upper()
        # Backwards compatibility with the old prompt values.
        if normalized == "SMB":
            normalized = "B2B"
        elif normalized == "CONSUMER":
            normalized = "B2C"
        return normalized if normalized in _VALID_B2B_B2C else "BOTH"

    @staticmethod
    def _normalize_jurisdiction(value: Any) -> str:
        normalized = str(value or "NO").strip().upper()
        if normalized in {"NO", "EU-EEA", "BOTH"}:
            return normalized
        return "NO"

    @staticmethod
    def _registry_match_is_target(query: str, stat_match: Optional[Any]) -> bool:
        if not stat_match:
            return False

        q = (query or "").lower()

        # A section request inside a matched statute is a direct document target.
        if re.search(r"§\s*\d+", q) or re.search(r"\bparagraf\s+\d+", q):
            return True

        document_type = getattr(stat_match, "document_type", "UNKNOWN")
        if document_type == "REGULATION" and re.search(r"\bforskrift(?:en|s)?\b", q):
            return True
        relation_markers = (
            "overgangsregel",
            "overgangsbestemm",
            "ikraft",
            "trer ",
            "endringene",
            "endring i",
            "implementering",
            "gebyr",
        )
        if document_type == "LAW" and any(marker in q for marker in relation_markers):
            return False

        alias = str(getattr(stat_match, "matched_alias", "") or "").lower().strip()
        if alias and alias in q:
            return True

        return False

    @staticmethod
    def _resolve_scope(
        query: str,
        stat_match: Optional[Any],
        parsed_scope: str,
    ) -> str:
        q = (query or "").lower()

        if re.search(r"§\s*\d+", q) or re.search(r"\bparagraf\s+\d+", q):
            return "SPECIFIC_PROVISION"

        broad_markers = (
            "hvilke forskrifter",
            "alle forskrifter",
            "oversikt over forskrifter",
            "oversikt over regler",
            "alle regler",
        )
        if any(marker in q for marker in broad_markers):
            return parsed_scope
        if re.search(r"\bforskrift\b", q):
            return "SPECIFIC_DOCUMENT"

        if re.search(r"\b(?:lov|forskrift|for|res)-\d{4}-\d{2}-\d{2}-\d+\b", q):
            return "SPECIFIC_DOCUMENT"

        if not stat_match:
            return parsed_scope

        document_type = getattr(stat_match, "document_type", "UNKNOWN")
        if document_type == "REGULATION" and re.search(r"\bforskrift(?:en|s)?\b", q):
            return "SPECIFIC_DOCUMENT"

        return parsed_scope
