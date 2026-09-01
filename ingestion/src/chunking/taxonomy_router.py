from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from rapidfuzz import fuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False

from openai import APIConnectionError, APIStatusError, AzureOpenAI, RateLimitError

from ingestion.models.legal_section import (
    EnrichedMilvusChunk,
    NormalizedLegalSection,
    SectionClassification,
    StructuralChunk,
)
from ingestion.src.config import (
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_CHAT_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AI_CONFIDENCE_THRESHOLD,
    AI_ROUTING_ENABLED,
    AI_SCOPE_VALIDATION_ENABLED,
)

logger = logging.getLogger(__name__)

TAXONOMY_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "taxonomies"

# Default domain legends fallback
DOMAIN_LEGEND: Dict[str, str] = {
    "D01_COMPANY": "Selskapsrett",
    "D02_MA": "Fusjon/Fisjon",
    "D03_ACCOUNTS": "Årsregnskap",
    "D04_CONTRACT": "Avtalerett",
    "D05_OBLIGATIONS": "Obligasjonsrett",
    "D06_DEBT": "Inkasso",
    "D07_INSOLVENCY": "Konkurs",
    "D08_MONETARY": "Pengekrav",
    "D09_SECURITY": "Panterett",
    "D10_DISPUTE": "Tvisteløsning",
    "D12_EMPLOYMENT": "Arbeidsrett",
    "D12_PRIVACY": "Personvern/GDPR",
}

@dataclass
class MappingDecision:
    mapping_status: str  # "PRODUCTION_MAPPED" | "MULTI_SUBDOMAIN_MAPPED" | "REVIEW_REQUIRED" | "UNMAPPED_REVIEW" | "OUT_OF_SCOPE"
    retrieval_enabled: bool  # True => proceed to Milvus; False => PostgreSQL RDB / Review queue
    domain_id: str  # e.g. "D12_EMPLOYMENT"
    primary_subdomain_id: Optional[str] = None  # e.g. "EL-02"
    subdomain_ids: List[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    jurisdiction: List[str] = field(default_factory=list)
    b2b_b2c: List[str] = field(default_factory=list)
    relationship_type: List[str] = field(default_factory=list)
    tier: int = 1


@dataclass
class SubdomainCandidate:
    subdomain_id: str
    subdomain_name: str
    keyword_score: float
    fuzzy_score: float
    profile_score: float
    combined_score: float
    routing_constraints: Dict[str, Any] = field(default_factory=dict)
    matched_keywords: List[str] = field(default_factory=list)
    raw_subdomain: Dict[str, Any] = field(default_factory=dict)


def has_scope_out_trigger(text: str, subdomain_raw: dict) -> Tuple[bool, str]:
    """
    Scans section text for scope_out topics or confuser terms.
    """
    text_lower = (text or "").lower()
    if not text_lower:
        return False, ""

    confusers = subdomain_raw.get("confusers", []) or []
    for c in confusers:
        term = str(c.get("term", "")).lower() if isinstance(c, dict) else str(c).lower()
        if term and term in text_lower:
            return True, f"confuser literal '{term}'"

    scope_out = subdomain_raw.get("scope_out", []) or []
    for item in scope_out:
        term = str(item.get("term", "") or item.get("topic", "") or item.get("name", "")).lower() if isinstance(item, dict) else str(item).lower()
        if not term:
            continue
        if term in text_lower:
            return True, f"scope_out term '{term}'"
        if _RAPIDFUZZ_AVAILABLE and len(term) >= 4 and fuzz.partial_ratio(text_lower, term) >= 85:
            return True, f"scope_out fuzzy term '{term}'"

    return False, ""


class AIValidator:

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        api_version: Optional[str] = None,
        chat_deployment: Optional[str] = None,
        confidence_threshold: float = AI_CONFIDENCE_THRESHOLD,
        routing_enabled: bool = AI_ROUTING_ENABLED,
        scope_validation_enabled: bool = AI_SCOPE_VALIDATION_ENABLED,
        winner_margin_threshold: float = 0.08,
    ) -> None:
        self.endpoint = endpoint or AZURE_OPENAI_ENDPOINT
        self.api_key = api_key or AZURE_OPENAI_KEY
        self.api_version = api_version or AZURE_OPENAI_API_VERSION
        self.chat_deployment = chat_deployment or AZURE_OPENAI_CHAT_DEPLOYMENT
        self.confidence_threshold = confidence_threshold
        self.routing_enabled = routing_enabled
        self.scope_validation_enabled = scope_validation_enabled
        self.winner_margin_threshold = winner_margin_threshold

        self._client: Optional[AzureOpenAI] = None
        self._init_client()

    def _init_client(self) -> None:
        if self.endpoint and self.api_key:
            try:
                self._client = AzureOpenAI(
                    azure_endpoint=self.endpoint,
                    api_key=self.api_key,
                    api_version=self.api_version,
                    timeout=20.0,
                    max_retries=0,
                )
            except Exception as e:
                logger.warning("AIValidator: AzureOpenAI client init failed: %s", e)

    def _wait_for_network_recovery(self, check_interval: float = 10.0) -> None:
        """Pauses execution and probes network connectivity until Wi-Fi / Internet is restored."""
        logger.warning("[NETWORK OFFLINE] AIValidator connection lost. Pausing AI routing. Waiting for Wi-Fi reconnection...")
        import socket
        while True:
            time.sleep(check_interval)
            is_online = False
            for host, port in [("8.8.8.8", 53), ("1.1.1.1", 53)]:
                try:
                    with socket.create_connection((host, port), timeout=4.0):
                        is_online = True
                        break
                except OSError:
                    pass

            if is_online:
                logger.info("[NETWORK RESTORED] Internet connection re-established. Resuming AIValidator...")
                self._init_client()
                return
            logger.warning("[WAITING FOR WI-FI] Still disconnected. Retrying in %ds...", int(check_interval))

    def prefilter_candidates(
        self,
        section_text: str,
        candidate_profiles: List[Dict[str, Any]],
        cross_refs: Optional[List[str]] = None,
        top_n: int = 3,
    ) -> List[Dict[str, Any]]:
        text_lower = section_text.lower()
        scored = []
        for p in candidate_profiles:
            subdomain_id = p.get("subdomain_id") or p.get("id")
            keywords = p.get("routing_keywords", []) or []
            matched_kw = [kw for kw in keywords if kw.lower() in text_lower]
            kw_score = min(len(matched_kw) * 0.25, 1.0)
            if _RAPIDFUZZ_AVAILABLE and keywords:
                fuzzy_scores = [fuzz.partial_ratio(text_lower, kw.lower()) for kw in keywords]
                fz_score = (max(fuzzy_scores) / 100.0) if fuzzy_scores else 0.0
            else:
                fz_score = 0.0

            combined = (kw_score * 0.5) + (fz_score * 0.5)

            if cross_refs:
                for ref in cross_refs:
                    if any(kw.lower() in ref.lower() for kw in keywords):
                        combined += 0.15
                        break

            triggered, _ = has_scope_out_trigger(section_text, p)
            if triggered:
                combined *= 0.1

            scored.append({
                "subdomain_id": subdomain_id,
                "name": p.get("name_en") or p.get("name_nb") or subdomain_id,
                "score": round(combined, 3),
                "profile": p,
                "matched_keywords": matched_kw,
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_n]

    def validate_candidate_scope(
        self,
        section_text: str,
        candidate: Dict[str, Any],
        domain_name: str,
    ) -> Dict[str, Any]:
        profile = candidate["profile"]
        scope_in = str(profile.get("scope_in", ""))[:1200]
        scope_out = str(profile.get("scope_out", ""))[:1200]

        system_prompt = (
            f"Du er en norsk juridisk taksonomiekspert for fagområdet {domain_name}.\n"
            f"Evaluér om lov- eller forskriftsbestemmelsen faller innenfor eller utenfor underområdet '{candidate['subdomain_id']}'.\n"
            "Svar KUN i gyldig JSON-format med feltene:\n"
            "{\n"
            '  "scope_in_match": true/false,\n'
            '  "scope_out_match": true/false,\n'
            '  "reason": "<kort begrunnelse på norsk>"\n'
            "}"
        )
        user_content = (
            f"Underområde: {candidate['subdomain_id']} ({candidate['name']})\n"
            f"Scope-In definisjon: {scope_in}\n"
            f"Scope-Out unntak: {scope_out}\n\n"
            f"Bestemmelsestekst:\n{section_text[:1500]}\n"
        )

        if not self.scope_validation_enabled or not self._client:
            return {
                "subdomain_id": candidate["subdomain_id"],
                "scope_in_match": True,
                "scope_out_match": False,
                "_hard_rejected": False,
                "reason": "Scope validation disabled or client missing",
            }

        attempt = 0
        while attempt < 3:
            try:
                response = self._client.chat.completions.create(
                    model=self.chat_deployment,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"},
                    max_tokens=200,
                )
                data = json.loads(response.choices[0].message.content)
                data["subdomain_id"] = candidate["subdomain_id"]
                data["_hard_rejected"] = bool(data.get("scope_out_match", False))
                return data
            except (APIConnectionError, ConnectionError, OSError) as conn_err:
                logger.warning("AIValidator Call 1 network lost (%s). Waiting for reconnection...", conn_err)
                self._wait_for_network_recovery()
                continue
            except RateLimitError as rl_err:
                logger.warning("AIValidator Call 1 rate limit (429). Backing off: %s", rl_err)
                time.sleep(5.0 * (attempt + 1))
                attempt += 1
            except Exception as e:
                logger.warning(f"AIValidator Call 1 error (attempt {attempt+1}/3): {e}")
                time.sleep(1.0 * (attempt + 1))
                attempt += 1

        return {
            "subdomain_id": candidate["subdomain_id"],
            "scope_in_match": False,
            "scope_out_match": False,
            "_hard_rejected": False,
            "reason": "API error fallback",
        }

    def arbitrate_routing(
        self,
        section_text: str,
        valid_candidates: List[Dict[str, Any]],
        domain_name: str,
    ) -> Dict[str, Any]:
        options_str = "\n".join(
            f"- ID: {c['subdomain_id']} | Name: {c['name']}" for c in valid_candidates
        )
        system_prompt = (
            f"Du er en norsk juridisk taksonomiekspert for fagområdet {domain_name}.\n"
            "Velg det mest presise underområdet for bestemmelsen fra kandidatlisten, "
            "eller oppgi 'NO_CONFIDENT_MATCH' dersom teksten er uklar eller tvetydig.\n"
            "Svar KUN i gyldig JSON-format med feltene:\n"
            "{\n"
            '  "selected_subdomain_ids": ["<ID>"],\n'
            '  "confidence": <flyttall mellom 0.0 og 1.0>,\n'
            '  "confuser_detected": true/false,\n'
            '  "reason": "<kort begrunnelse på norsk>"\n'
            "}"
        )
        user_content = (
            f"Bestemmelsestekst:\n{section_text[:1500]}\n\n"
            f"Gyldige kandidat-underområder:\n{options_str}\n\n"
            "Velg underområdet som best dekker denne bestemmelsen."
        )

        if not self.routing_enabled or not self._client:
            first_id = valid_candidates[0]["subdomain_id"] if valid_candidates else "NO_CONFIDENT_MATCH"
            return {
                "selected_subdomain_ids": [first_id] if first_id != "NO_CONFIDENT_MATCH" else [],
                "confidence": 0.85,
                "confuser_detected": False,
                "reason": "Routing disabled or client missing",
            }

        attempt = 0
        while attempt < 3:
            try:
                response = self._client.chat.completions.create(
                    model=self.chat_deployment,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"},
                    max_tokens=250,
                )
                data = json.loads(response.choices[0].message.content)
                return data
            except (APIConnectionError, ConnectionError, OSError) as conn_err:
                logger.warning("⚠️ AIValidator Call 2 network lost (%s). Waiting for reconnection...", conn_err)
                self._wait_for_network_recovery()
                continue
            except RateLimitError as rl_err:
                logger.warning("⚠️ AIValidator Call 2 rate limit (429). Backing off: %s", rl_err)
                time.sleep(5.0 * (attempt + 1))
                attempt += 1
            except Exception as e:
                logger.warning(f"AIValidator Call 2 error (attempt {attempt+1}/3): {e}")
                time.sleep(1.0 * (attempt + 1))
                attempt += 1

        return {
            "selected_subdomain_ids": [],
            "confidence": 0.0,
            "confuser_detected": False,
            "reason": "API error fallback",
        }

    def arbitrate_subdomain(
        self,
        section_heading: str,
        section_text: str,
        candidate_profiles: List[Dict[str, Any]],
        domain_name: str,
    ) -> Optional[Tuple[str, float, str]]:
        valid_candidates = []
        for p in candidate_profiles:
            sid = p.get("subdomain_id") or p.get("id")
            if sid:
                valid_candidates.append({
                    "subdomain_id": sid,
                    "name": p.get("name_en") or p.get("name_nb") or sid,
                    "profile": p,
                })
        if not valid_candidates:
            return None

        combined_text = f"{section_heading}\n\n{section_text}" if section_heading else section_text
        res = self.arbitrate_routing(combined_text, valid_candidates, domain_name)
        sids = res.get("selected_subdomain_ids", [])
        if sids and sids[0] != "NO_CONFIDENT_MATCH":
            return (sids[0], float(res.get("confidence", 0.85)), str(res.get("reason", "")))
        return None

    def validate_scope(
        self,
        subdomain_id: str,
        subdomain_name: str,
        section_text: str,
        scope_in: str,
        scope_out: str,
    ) -> Optional[Dict[str, Any]]:
        cand = {
            "subdomain_id": subdomain_id,
            "name": subdomain_name,
            "profile": {"scope_in": scope_in, "scope_out": scope_out},
        }
        res = self.validate_candidate_scope(section_text, cand, subdomain_name)
        return res

    def evaluate_section(
        self,
        section_chunk: Any,
        candidate_profiles: List[Dict[str, Any]],
        domain_id: str,
        domain_name: str = "Juridisk domene",
        document_type: str = "LAW",
    ) -> MappingDecision:
        if hasattr(section_chunk, "source_text"):
            section_text = getattr(section_chunk, "source_text", "")
            cross_refs = getattr(section_chunk, "cross_refs", []) or []
        else:
            section_text = section_chunk.get("source_text", "") or section_chunk.get("text", "")
            cross_refs = section_chunk.get("cross_refs", []) or []

        candidates = self.prefilter_candidates(section_text, candidate_profiles, cross_refs=cross_refs)

        if not candidates:
            return MappingDecision(
                mapping_status="UNMAPPED_REVIEW",
                retrieval_enabled=False,
                domain_id=domain_id,
                confidence=0.0,
                reasoning="No candidate subdomains matched pre-filtering criteria",
                jurisdiction=[],
                b2b_b2c=[],
                relationship_type=[],
                tier=1 if document_type == "LAW" else 2,
            )

        scope_results = []
        for c in candidates:
            res = self.validate_candidate_scope(section_text, c, domain_name)
            scope_results.append(res)

        passed_ids = {
            r["subdomain_id"] for r in scope_results
            if r.get("scope_in_match") and not r.get("_hard_rejected")
        }
        valid_candidates = [c for c in candidates if c["subdomain_id"] in passed_ids]

        if not valid_candidates:
            return MappingDecision(
                mapping_status="UNMAPPED_REVIEW",
                retrieval_enabled=False,
                domain_id=domain_id,
                confidence=0.0,
                reasoning="No candidate passed AI Call 1 scope validation",
                evidence={"scope_results": scope_results},
                jurisdiction=[],
                b2b_b2c=[],
                relationship_type=[],
                tier=1 if document_type == "LAW" else 2,
            )

        routing_res = self.arbitrate_routing(section_text, valid_candidates, domain_name)
        selected_ids = routing_res.get("selected_subdomain_ids", [])
        confidence = float(routing_res.get("confidence", 0.0))
        confuser_flag = bool(routing_res.get("confuser_detected", False))

        margin_ok = True
        if len(valid_candidates) >= 2:
            delta = abs(valid_candidates[0]["score"] - valid_candidates[1]["score"])
            if delta < self.winner_margin_threshold and confidence < 0.90:
                margin_ok = False

        primary_id = selected_ids[0] if selected_ids and selected_ids != ["NO_CONFIDENT_MATCH"] else None

        winner_profile = None
        for c in valid_candidates:
            if c["subdomain_id"] == primary_id:
                winner_profile = c["profile"]
                break

        if winner_profile:
            constraints = winner_profile.get("routing_constraints", {}) or {}
            raw_jurisdiction = constraints.get("jurisdiction", [])
            jurisdiction = raw_jurisdiction if isinstance(raw_jurisdiction, list) else ([raw_jurisdiction] if raw_jurisdiction else [])
            raw_b2b_b2c = constraints.get("b2b_b2c", [])
            b2b_b2c = raw_b2b_b2c if isinstance(raw_b2b_b2c, list) else ([raw_b2b_b2c] if raw_b2b_b2c else [])
            raw_rel = constraints.get("relationship_type", [])
            relationship_type = raw_rel if isinstance(raw_rel, list) else ([raw_rel] if raw_rel else [])
            tier_ceiling = constraints.get("tier_ceiling", 1 if document_type == "LAW" else 2)
            tier = min(1 if document_type == "LAW" else 2, tier_ceiling)
        else:
            jurisdiction = []
            b2b_b2c = []
            relationship_type = []
            tier = 1 if document_type == "LAW" else 2

        is_confident = (
            selected_ids
            and selected_ids != ["NO_CONFIDENT_MATCH"]
            and confidence >= self.confidence_threshold
            and not confuser_flag
            and margin_ok
        )

        status = "PRODUCTION_MAPPED" if len(selected_ids) == 1 else "MULTI_SUBDOMAIN_MAPPED"

        if is_confident:
            return MappingDecision(
                mapping_status=status,
                retrieval_enabled=True,
                domain_id=domain_id,
                primary_subdomain_id=primary_id,
                subdomain_ids=selected_ids,
                confidence=confidence,
                reasoning=routing_res.get("reason", ""),
                evidence={"scope_results": scope_results, "routing_result": routing_res},
                jurisdiction=jurisdiction,
                b2b_b2c=b2b_b2c,
                relationship_type=relationship_type,
                tier=tier,
            )
        else:
            return MappingDecision(
                mapping_status="REVIEW_REQUIRED",
                retrieval_enabled=False,
                domain_id=domain_id,
                primary_subdomain_id=primary_id,
                subdomain_ids=selected_ids,
                confidence=confidence,
                reasoning=routing_res.get("reason", "Low confidence, confuser detected, or winner margin too small"),
                evidence={"scope_results": scope_results, "routing_result": routing_res},
                jurisdiction=jurisdiction,
                b2b_b2c=b2b_b2c,
                relationship_type=relationship_type,
                tier=tier,
            )


class TaxonomyRouter:
    WEIGHT_KEYWORD: float = 0.40
    WEIGHT_FUZZY: float = 0.25
    WEIGHT_PROFILE: float = 0.35

    def __init__(
        self,
        domain_legend: Optional[Dict[str, str]] = None,
        taxonomies_dir: Optional[Path] = None,
        ai_validator: Optional[AIValidator] = None,
    ):
        self.legend = domain_legend or DOMAIN_LEGEND
        self.taxonomies_dir = taxonomies_dir or TAXONOMY_DIR
        self.ai_validator = ai_validator or AIValidator()
        self._domains: Dict[str, Dict[str, Any]] = {}
        self._taxonomy_versions: Dict[str, str] = {}
        self._load_taxonomies()

    def _load_taxonomies(self) -> None:
        """Loads canonical taxonomy JSON files from configs/taxonomies/."""
        if not self.taxonomies_dir.exists():
            logger.warning("Taxonomies directory does not exist: %s", self.taxonomies_dir)
            return

        json_files = list(self.taxonomies_dir.glob("*.json"))
        for jf in json_files:
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                version = data.get("taxonomy_version", "1.0.1")
                domains = data.get("domains", [])
                for dom in domains:
                    dom_id = dom.get("domain_id")
                    if dom_id:
                        dom["_taxonomy_version"] = version
                        self._domains[dom_id] = dom
                        self._taxonomy_versions[dom_id] = version
                logger.info("TaxonomyRouter: Loaded %d domains from %s (v%s)", len(domains), jf.name, version)
            except Exception as exc:
                logger.error("TaxonomyRouter: Failed to load taxonomy file %s: %s", jf, exc)

    def _calculate_keyword_score(self, text_lower: str, keywords: List[str]) -> Tuple[float, List[str]]:
        """Matches exact keywords/phrases against text."""
        if not keywords:
            return 0.0, []
        matched = []
        for kw in keywords:
            kw_clean = kw.strip().lower()
            if kw_clean and kw_clean in text_lower:
                matched.append(kw)
        score = min(1.0, len(matched) / max(1, min(len(keywords), 4)))
        return score, matched

    def _matches_required_sources(self, section_ref: str, subdomain: Dict[str, Any]) -> bool:
        """Checks if the section reference falls within required_sources key_sections."""
        if not section_ref:
            return False

        sec_num_match = re.search(r"§\s*(\d+)(?:-(\d+))?", section_ref)
        if not sec_num_match:
            return False

        sec_chap = int(sec_num_match.group(1))
        sec_para = int(sec_num_match.group(2)) if sec_num_match.group(2) else None

        req_sources = subdomain.get("required_sources", [])
        for src in req_sources:
            key_secs = src.get("key_sections", "")
            if not key_secs:
                continue

            # Pattern like "§§ 15-1 – 15-17" or "§§ 14-1 – 14-13" or "§§ 10-1 – 10-14"
            range_match = re.search(r"§§?\s*(\d+)-(\d+)\s*[–-]\s*(\d+)-(\d+)", key_secs)
            if range_match:
                start_chap, start_p, end_chap, end_p = map(int, range_match.groups())
                if sec_chap == start_chap == end_chap and sec_para is not None:
                    if start_p <= sec_para <= end_p:
                        return True

            # Pattern like "§§ 10–27"
            range_single = re.search(r"§§?\s*(\d+)\s*[–-]\s*(\d+)", key_secs)
            if range_single and sec_para is None:
                start_s, end_s = map(int, range_single.groups())
                if start_s <= sec_chap <= end_s:
                    return True

        return False

    def _calculate_fuzzy_score(self, text_lower: str, heading_lower: str, keywords: List[str]) -> float:
        """Calculates fuzzy token set ratio score across keywords against heading and text."""
        if not keywords or not _RAPIDFUZZ_AVAILABLE:
            return 0.0

        best_score = 0.0

        # Check against heading first (very strong signal)
        if heading_lower:
            for kw in keywords:
                ratio = fuzz.token_set_ratio(kw.lower(), heading_lower) / 100.0
                if ratio > best_score:
                    best_score = ratio

        # Check against first 500 chars of text
        sample = text_lower[:500]
        for kw in keywords[:8]:
            ratio = fuzz.token_set_ratio(kw.lower(), sample) / 100.0
            if ratio > 0.75 and ratio > best_score:
                best_score = ratio

        return best_score if best_score >= 0.70 else 0.0

    def _calculate_profile_score(self, text_lower: str, subdomain: Dict[str, Any]) -> float:
        """Calculates token overlap with subdomain name and scope_in keywords."""
        scope_in = subdomain.get("scope_in", [])
        name_nb = subdomain.get("name_nb", "")
        profile_text = (name_nb + " " + " ".join(scope_in)).lower()
        profile_words = set(re.findall(r"\b[a-zæøå]{5,}\b", profile_text))
        if not profile_words:
            return 0.0

        text_words = set(re.findall(r"\b[a-zæøå]{5,}\b", text_lower))
        overlap = len(profile_words.intersection(text_words))
        return min(1.0, overlap / max(4, len(profile_words) * 0.3))

    def rank_subdomains(
        self,
        domain_id: str,
        section_text: str,
        section_heading: str = "",
        section_ref: str = "",
    ) -> List[SubdomainCandidate]:
        """Ranks all subdomains under a domain against section text."""
        domain_data = self._domains.get(domain_id)
        if not domain_data:
            return []

        subdomains = domain_data.get("subdomains", [])
        if not subdomains:
            return []

        combined_text = f"{section_heading} {section_text}".lower()
        heading_lower = section_heading.lower()
        candidates: List[SubdomainCandidate] = []

        for sub in subdomains:
            sid = sub.get("subdomain_id", "")
            sname = sub.get("name_nb") or sub.get("name_en") or sid
            keywords = sub.get("routing_keywords", [])
            constraints = sub.get("routing_constraints", {})

            # 1. Authoritative Key Section Match
            is_key_section = self._matches_required_sources(section_ref, sub)

            # 2. Keyword & Fuzzy Scores
            kw_score, matched_kws = self._calculate_keyword_score(combined_text, keywords)
            fuzzy_score = self._calculate_fuzzy_score(combined_text, heading_lower, keywords)
            profile_score = self._calculate_profile_score(combined_text, sub)

            if is_key_section:
                combined_score = 0.95
            elif kw_score > 0:
                combined_score = 0.50 * kw_score + 0.30 * fuzzy_score + 0.20 * profile_score
            elif fuzzy_score >= 0.75:
                combined_score = 0.40 * fuzzy_score + 0.20 * profile_score
            else:
                combined_score = 0.0

            if combined_score >= 0.20 or is_key_section:
                candidates.append(
                    SubdomainCandidate(
                        subdomain_id=sid,
                        subdomain_name=sname,
                        keyword_score=kw_score if not is_key_section else 1.0,
                        fuzzy_score=fuzzy_score,
                        profile_score=profile_score,
                        combined_score=combined_score,
                        routing_constraints=constraints,
                        matched_keywords=matched_kws,
                        raw_subdomain=sub,
                    )
                )

        candidates.sort(key=lambda c: c.combined_score, reverse=True)
        return candidates

    def classify(
        self,
        chunk: StructuralChunk,
        candidate_domain_ids: List[str],
        section_heading: str = "",
        document_type: str = "LAW",
    ) -> List[SectionClassification]:
        valid_candidates = [
            d for d in candidate_domain_ids
            if d and d not in ("OUT_OF_SCOPE", "NEEDS_ROUTING", "NEEDS_VERIFICATION")
        ]

        if not valid_candidates:
            return [
                SectionClassification(
                    domain_id="UNMAPPED",
                    domain_name="Unmapped",
                    subdomain_id=None,
                    subdomain_name=None,
                    subdomain_ids=[],
                    subdomain_names=[],
                    jurisdiction=[],
                    b2b_b2c=[],
                    relationship_type=[],
                    tier=1 if document_type == "LAW" else 2,
                    confidence=0.0,
                    vdb_eligible=False,
                )
            ]

        results: List[SectionClassification] = []
        for dom_id in valid_candidates:
            domain_name = self.legend.get(dom_id, dom_id)
            subdomain_candidates = self.rank_subdomains(
                domain_id=dom_id,
                section_text=chunk.source_text,
                section_heading=section_heading,
                section_ref=chunk.section_ref,
            )
            tax_version = self._taxonomy_versions.get(dom_id, "1.0.1")

            if subdomain_candidates and subdomain_candidates[0].combined_score > 0.15:
                best = subdomain_candidates[0]

                # TIER 2: AI CALL 1 - LLM Subdomain Arbiter
                has_competing_tie = (
                    len(subdomain_candidates) >= 2
                    and subdomain_candidates[0].keyword_score > 0
                    and subdomain_candidates[1].keyword_score > 0
                    and abs(subdomain_candidates[0].combined_score - subdomain_candidates[1].combined_score) < 0.04
                )

                if has_competing_tie and self.ai_validator.routing_enabled:
                    ai_arb = self.ai_validator.arbitrate_subdomain(
                        section_heading=section_heading,
                        section_text=chunk.source_text,
                        candidate_profiles=[c.raw_subdomain for c in subdomain_candidates[:4] if c.raw_subdomain],
                        domain_name=domain_name,
                    )
                    if ai_arb:
                        chosen_id, ai_conf, ai_reason = ai_arb
                        for c in subdomain_candidates:
                            if c.subdomain_id == chosen_id:
                                best = c
                                best.combined_score = max(best.combined_score, ai_conf)
                                logger.debug("AI Arbiter selected %s for %s (%s)", chosen_id, section_heading, ai_reason)
                                break

                # Check for multiple qualifying subdomains
                qualifying = [c for c in subdomain_candidates if c.combined_score >= max(0.20, best.combined_score * 0.80)]
                selected_sub_ids = [c.subdomain_id for c in qualifying]
                selected_sub_names = [c.subdomain_name for c in qualifying]

                constraints = best.routing_constraints or {}
                raw_jurisdiction = constraints.get("jurisdiction", [])
                jurisdiction = raw_jurisdiction if isinstance(raw_jurisdiction, list) else ([raw_jurisdiction] if raw_jurisdiction else [])
                raw_b2b_b2c = constraints.get("b2b_b2c", [])
                b2b_b2c = raw_b2b_b2c if isinstance(raw_b2b_b2c, list) else ([raw_b2b_b2c] if raw_b2b_b2c else [])
                raw_rel = constraints.get("relationship_type", [])
                relationship_type = raw_rel if isinstance(raw_rel, list) else ([raw_rel] if raw_rel else [])
                tier_ceiling = constraints.get("tier_ceiling", 1 if document_type == "LAW" else 2)
                tier = min(1 if document_type == "LAW" else 2, tier_ceiling)

                # TIER 2: AI CALL 2 - LLM Scope & Constraint Validator
                scope_out_raw = best.raw_subdomain.get("scope_out", []) if best.raw_subdomain else []
                scope_out_list = scope_out_raw if isinstance(scope_out_raw, list) else [str(scope_out_raw)]
                has_scope_conflict = bool(
                    scope_out_list
                    and any(so.lower() in chunk.source_text.lower() for so in scope_out_list if len(so) > 3)
                )

                if self.ai_validator.scope_validation_enabled and has_scope_conflict and best.raw_subdomain:
                    scope_val = self.ai_validator.validate_scope(
                        subdomain_id=best.subdomain_id,
                        subdomain_name=best.subdomain_name,
                        section_text=chunk.source_text,
                        scope_in=str(best.raw_subdomain.get("scope_in", "")),
                        scope_out="; ".join(scope_out_list),
                    )
                    if scope_val and isinstance(scope_val, dict):
                        if scope_val.get("jurisdiction"):
                            jurisdiction = scope_val["jurisdiction"]
                        if scope_val.get("b2b_b2c"):
                            b2b_b2c = scope_val["b2b_b2c"]
                        if scope_val.get("relationship_type"):
                            relationship_type = scope_val["relationship_type"]

                # Decision Engine Evaluation
                winner_margin_ok = True
                if len(subdomain_candidates) >= 2:
                    delta = abs(subdomain_candidates[0].combined_score - subdomain_candidates[1].combined_score)
                    if delta < self.ai_validator.winner_margin_threshold and best.combined_score < 0.90:
                        winner_margin_ok = False

                retrieval_enabled = best.combined_score >= 0.20 and winner_margin_ok and bool(best.subdomain_id and best.subdomain_id != "NO_SUBDOMAIN")
                results.append(
                    SectionClassification(
                        domain_id=dom_id,
                        domain_name=domain_name,
                        subdomain_id=best.subdomain_id,
                        subdomain_name=best.subdomain_name,
                        subdomain_ids=selected_sub_ids,
                        subdomain_names=selected_sub_names,
                        jurisdiction=jurisdiction,
                        b2b_b2c=b2b_b2c,
                        relationship_type=relationship_type,
                        tier=tier,
                        taxonomy_version=tax_version,
                        confidence=best.combined_score,
                        vdb_eligible=retrieval_enabled,
                    )
                )
            else:
                results.append(
                    SectionClassification(
                        domain_id=dom_id,
                        domain_name=domain_name,
                        subdomain_id=None,
                        subdomain_name=None,
                        subdomain_ids=[],
                        subdomain_names=[],
                        jurisdiction=[],
                        b2b_b2c=[],
                        relationship_type=[],
                        tier=1 if document_type == "LAW" else 2,
                        taxonomy_version=tax_version,
                        confidence=0.0,
                        vdb_eligible=False,
                    )
                )
        return results


class ChunkEnricher:
    @staticmethod
    def enrich(
        section: NormalizedLegalSection,
        chunk: StructuralChunk,
        classification: SectionClassification,
    ) -> EnrichedMilvusChunk:
        """
        Combines section metadata, chunk text, and taxonomy classification into an EnrichedMilvusChunk.
        """
        header_tag = f"[{section.document_type.upper()}]"
        parts = [header_tag]
        if section.document_title:
            parts.append(section.document_title)

        if section.chapter_number and section.chapter_title:
            parts.append(f"{section.chapter_number} - {section.chapter_title}")
        elif section.chapter_number:
            parts.append(section.chapter_number)
        elif section.chapter_title:
            parts.append(section.chapter_title)

        if section.section_title and section.section_title.strip() != section.section_number.strip():
            parts.append(f"{section.section_number} - {section.section_title}")
        else:
            parts.append(section.section_number)

        parts.append(chunk.source_text)
        embedding_text = "\n".join(p for p in parts if p.strip()).strip()

        subdomain_id = classification.subdomain_id or "NO_SUBDOMAIN"
        subdomain_name = classification.subdomain_name or ""
        subdomain_ids = classification.subdomain_ids or ([subdomain_id] if subdomain_id != "NO_SUBDOMAIN" else [])
        subdomain_names = classification.subdomain_names or ([subdomain_name] if subdomain_name else [])

        chunk_id = build_chunk_id(
            canonical_document_id=section.canonical_document_id,
            source_section_key=section.source_section_key,
            domain_id=classification.domain_id,
            subdomain_id=classification.subdomain_id,
            chunk_index=chunk.chunk_index,
        )

        return EnrichedMilvusChunk(
            chunk_id=chunk_id,
            embedding_text=embedding_text,
            source_text=chunk.source_text,
            domain_id=classification.domain_id,
            domain_name=classification.domain_name,
            subdomain_id=subdomain_id,
            subdomain_name=subdomain_name,
            subdomain_ids=subdomain_ids,
            subdomain_names=subdomain_names,
            canonical_document_id=section.canonical_document_id,
            legal_section_id=section.source_section_key.replace("/", "-"),
            source_section_key=section.source_section_key,
            document_type=section.document_type,
            doc_title=section.document_title,
            section_number=section.section_number,
            section_title=section.section_title or section.section_number,
            citation_anchor=section.section_number,
            source_url=section.source_url or "",
            token_count=chunk.token_count,
            chunk_index=chunk.chunk_index,
            content_hash=section.source_content_hash,
            jurisdictions=classification.jurisdiction,
            b2b_b2c_types=classification.b2b_b2c,
            relationship_types=classification.relationship_type,
            parent_law_canonical_id="",
            parent_law_title="",
            source_type="lov" if section.document_type == "LAW" else "forskrift",
            tier=classification.tier,
            language="no",
            version_date=section.version_date or "",
            taxonomy_version=classification.taxonomy_version,
            metadata={
                "source_block_start": chunk.source_block_start,
                "source_block_end": chunk.source_block_end,
                "is_definition": chunk.is_definition,
                "cross_refs": chunk.cross_refs,
                "taxonomy_version": classification.taxonomy_version,
            },
        )


def build_chunk_id(
    canonical_document_id: str,
    source_section_key: str,
    domain_id: str,
    subdomain_id: Optional[str],
    chunk_index: int,
) -> str:
    """
    Constructs deterministic chunk ID:
    {canonical_document_id}__{source_section_key}__{domain_id}__{subdomain_id_or_NO_SUBDOMAIN}__{chunk_index:04d}
    """
    clean_canon = re.sub(r"[^A-Za-z0-9_\-]+", "_", canonical_document_id).strip("_")
    clean_sec = re.sub(r"[^A-Za-z0-9_\-]+", "-", source_section_key.replace("§", "paragraf-")).strip("-")
    sub_tag = subdomain_id if subdomain_id and subdomain_id.strip() else "NO_SUBDOMAIN"
    return f"{clean_canon}__{clean_sec}__{domain_id}__{sub_tag}__{chunk_index:04d}"
