import asyncio
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings
from config_domains import (
    DOMAINS_CANONICAL,
    VALID_B2B_B2C,
    VALID_JURISDICTIONS,
    VALID_REL_TYPES,
    normalize_domain,
)
from router.taxonomy_loader import taxonomy_loader
from prompts.router_prompts import ROUTER_BASE_PROMPT
from utils.json_response_parser import parse_json_response

logger = logging.getLogger(__name__)

# ── NAMED CONSTANTS ──────────────────────────────────────────────────
MIN_CONFIDENCE_THRESHOLD = 0.6
MAX_RETRIES = 2
RETRY_DELAY = 0.5


class RouterResult(BaseModel):
    domain: Optional[str] = Field(default=None)
    subdomain_candidates: List[str] = Field(default_factory=list)
    b2b_b2c: str = Field(default="BOTH")
    relationship_type: str = Field(default="commercial")
    jurisdiction: str = Field(default="NO")
    matched_keywords: List[str] = Field(default_factory=list)
    conflict_detected: bool = Field(default=False)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    low_confidence_fallback: bool = Field(default=False)


class RouterAgent:

    def __init__(self, llm: Optional[Any] = None) -> None:
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
        # Dynamically derive taxonomy text & subdomains from single source-of-truth taxonomy_loader
        self._taxonomy_text, self._valid_subdomains = self._build_derived_taxonomy()
        self._system_prompt = (
            f"{ROUTER_BASE_PROMPT}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"TAXONOMY\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{self._taxonomy_text}\n"
        )
        logger.info("[OK] RouterAgent initialized with dynamic taxonomy derivation")

    def _build_derived_taxonomy(self) -> (str, Dict[str, List[str]]):
        """Derives taxonomy prompt text and valid subdomain lists from taxonomy_loader."""
        subdomain_map: Dict[str, List[str]] = {}
        prompt_lines: List[str] = []

        all_domains = taxonomy_loader._domains
        for d_id, d in all_domains.items():
            d_title = d.get("name_nb") or d.get("name_en") or d_id
            canon_key = normalize_domain(d_title) or normalize_domain(d_id) or d_id.lower()
            sub_ids = d.get("subdomains", [])

            sub_labels = []
            kw_list = []
            for sub_id in sub_ids:
                sub_data = taxonomy_loader.get_subdomain(sub_id)
                if sub_data:
                    label = sub_data.get("name_en") or sub_id
                    sub_labels.append(label)
                    kw_list.extend(sub_data.get("routing_keywords", []))

            for key in (canon_key, d_title.lower(), d_id.lower(), d_id):
                if key not in subdomain_map:
                    subdomain_map[key] = []
                subdomain_map[key].extend(list(dict.fromkeys(sub_labels)))

            kw_str = ", ".join(list(dict.fromkeys(kw_list))[:12])

            prompt_lines.append(f"DOMAIN: {d_title} (key: {canon_key})")
            prompt_lines.append("SUBDOMAINS:")
            for sl in sub_labels:
                prompt_lines.append(f"  - {sl}")
            if kw_str:
                prompt_lines.append(f"KEYWORDS: {kw_str}")
            prompt_lines.append("")

        return "\n".join(prompt_lines), subdomain_map





    async def route(
        self,
        user_query: str = "",
        enriched_query: str = "",
        domain_hint: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        raw_query: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:

        query = user_query or raw_query or ""
        logger.info(f"RouterAgent: routing query '{query[:60]}'")

        query_text = f"USER QUERY: {query}\nENRICHED QUERY: {enriched_query}"
        if domain_hint:
            query_text += f"\nDOMAIN HINT: {domain_hint}"


        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=query_text),
        ]

        # LLM Execution with exponential backoff retries
        response = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._llm.agenerate([messages])
                break
            except Exception as exc:
                if attempt < MAX_RETRIES:
                    logger.warning(f"⚠️ RouterAgent: attempt {attempt + 1} failed: {exc}. Retrying...")
                    await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                else:
                    logger.error(f"❌ RouterAgent: LLM execution failed after retries: {exc}")

        # Parse JSON with project-wide JsonResponseParser & RouterResult validation
        if response and response.generations and response.generations[0]:
            raw_text = response.generations[0][0].text.strip()
            parsed_data = parse_json_response(raw_text)

            if parsed_data:
                raw_domain = parsed_data.get("domain")
                norm_domain = normalize_domain(raw_domain) or domain_hint

                # Validate subdomains against derived single-source subdomain map
                raw_subs = parsed_data.get("subdomain_candidates", [])
                valid_subs = []
                if norm_domain in self._valid_subdomains:
                    allowed = set(self._valid_subdomains[norm_domain])
                    allowed_lower = {s.lower(): s for s in allowed}
                    for s in raw_subs:
                        if s in allowed:
                            valid_subs.append(s)
                        elif s.lower() in allowed_lower:
                            valid_subs.append(allowed_lower[s.lower()])
                else:
                    # Keep raw subdomains if domain key is not in static validation map
                    valid_subs = [str(s) for s in raw_subs]


                confidence = float(parsed_data.get("confidence", 0.85))

                b2b_b2c = str(parsed_data.get("b2b_b2c", "BOTH")).upper()
                if b2b_b2c not in VALID_B2B_B2C:
                    b2b_b2c = "BOTH"

                rel_type = str(parsed_data.get("relationship_type", "commercial")).lower()
                if rel_type not in VALID_REL_TYPES:
                    rel_type = "commercial"

                jurisdiction = str(parsed_data.get("jurisdiction", "NO")).upper()
                if jurisdiction not in VALID_JURISDICTIONS:
                    jurisdiction = "NO"

                # Low-Confidence Routing Fallback Strategy (< 0.6)
                low_conf_fallback = False
                if confidence < MIN_CONFIDENCE_THRESHOLD:
                    logger.warning(
                        f"⚠️ RouterAgent: low confidence score ({confidence:.2f} < {MIN_CONFIDENCE_THRESHOLD}) "
                        f"— triggering domain-level broad search fallback"
                    )
                    valid_subs = []  # Clear restricted subdomains to force broad search
                    low_conf_fallback = True

                result = RouterResult(
                    domain=norm_domain,
                    subdomain_candidates=valid_subs,
                    b2b_b2c=b2b_b2c,
                    relationship_type=rel_type,
                    jurisdiction=jurisdiction,
                    matched_keywords=parsed_data.get("matched_keywords", []),
                    conflict_detected=bool(parsed_data.get("conflict_detected", False)),
                    confidence=confidence,
                    low_confidence_fallback=low_conf_fallback,
                )

                logger.info(
                    f"RouterAgent: domain={result.domain} | subdomains={result.subdomain_candidates} | "
                    f"confidence={result.confidence:.2f} | low_conf_fallback={result.low_confidence_fallback}"
                )
                return result.model_dump()

        # Fallback Result
        fallback_domain = normalize_domain(domain_hint)
        fallback_result = RouterResult(
            domain=fallback_domain,
            subdomain_candidates=[],
            confidence=0.5,
            low_confidence_fallback=True,
        )
        return fallback_result.model_dump()

    async def run(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Backward-compatible alias for route()."""
        return await self.route(*args, **kwargs)