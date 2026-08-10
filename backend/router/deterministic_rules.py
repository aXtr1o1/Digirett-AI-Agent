"""
router/deterministic_rules.py — Data-Driven Modular Rule Registry for Legal Routing
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional
from router.utils.keyword_matcher import KeywordMatcher
from router.utils.models import RoutingDecision

logger = logging.getLogger(__name__)

_RULES_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "registry",
    "deterministic_rules.json",
)


class DeterministicRules:
    _metrics: Dict[str, int] = {}
    _json_rules: List[Dict] = []

    @classmethod
    def _load_json_rules(cls) -> None:
        if cls._json_rules:
            return
        if os.path.exists(_RULES_JSON_PATH):
            try:
                with open(_RULES_JSON_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cls._json_rules = data.get("rules", [])
            except Exception as exc:
                logger.error(f"❌ Failed to load deterministic rules JSON: {exc}")

    @classmethod
    def evaluate(cls, query: str) -> Optional[str]:
        decision = cls.evaluate_detailed(query)
        return decision.route if decision else None

    @classmethod
    def evaluate_detailed(cls, query: str) -> Optional[RoutingDecision]:
        if not query:
            return None

        cls._load_json_rules()

        # 1. Data-Driven Rules from JSON asset
        for r_item in cls._json_rules:
            r_id = r_item.get("rule_id", "json_rule")
            kws = r_item.get("keywords", [])
            route = r_item.get("route")
            if route and KeywordMatcher.any(query, kws):
                cls._metrics[r_id] = cls._metrics.get(r_id, 0) + 1
                logger.info(f"⚡ Deterministic rule hit ({r_id}) -> {route}")
                return RoutingDecision(route=route, reason=f"Data-driven rule: {r_id}", confidence=1.0)

        # 2. Contextual Rules
        q_lower = query.lower()

        # Contract precedence overrides
        if KeywordMatcher.any(query, ["avtale", "kontrakt", "tilbud", "aksept", "fullmakt", "ugyldig", "angrerett", "nettbutikk"]):
            if KeywordMatcher.any(query, ["angrerett", "e-handel", "ordreknapp", "kjøpsknapp", "nettbutikk", "abonnement"]):
                return RoutingDecision(route="CL-05", reason="Contract eCom rule")
            if KeywordMatcher.any(query, ["standardvilkår", "salgsbetingelser", "innkjøpsvilkår", "click-wrap", "lenke", "referanse"]):
                return RoutingDecision(route="CL-04", reason="Contract terms rule")
            if KeywordMatcher.any(query, ["ugyldig", "svik", "villfarelse", "trusler", "lempes", "lemping", "revideres", "bristet", "utnyttet", "presset", "markedsføringsloven"]):
                return RoutingDecision(route="CL-03", reason="Contract invalidity rule")
            if KeywordMatcher.any(query, ["fullmakt", "spesialfullmakt", "prokura", "overskrider", "firmaattest", "fellesskap"]):
                return RoutingDecision(route="CL-02", reason="Contract proxy rule")
            if KeywordMatcher.any(query, ["muntlig", "aksepterte", "bindende", "akseptfrist", "rimelig tid", "mottilbud", "passivitet", "stilltiende", "e-post"]):
                return RoutingDecision(route="CL-01", reason="Contract formation rule")

        # Employment precedence overrides
        if KeywordMatcher.any(query, ["arbeidsavtale", "arbeidskontrakt", "oppsigelse", "ansatt", "overtid", "ferie", "vikariat"]):
            if KeywordMatcher.any(query, ["søksmål", "forliksråd", "prosessvarsel", "saksomkostninger", "tvist", "forføyning"]):
                return RoutingDecision(route="EL-05", reason="Employment dispute rule")
            if KeywordMatcher.any(query, ["overtid", "ferie", "skift", "turnus", "hviletid", "pauser", "gjennommssnittsberegning", "arbeidstid"]):
                return RoutingDecision(route="EL-03", reason="Employment hours rule")
            if KeywordMatcher.any(query, ["prøvetid", "midlertidig", "vikariat", "stillingsprosent", "innleie", "konkurranseklausul", "styringsrett", "skriftlig"]):
                return RoutingDecision(route="EL-01", reason="Employment formation rule")

        # Foreldelse
        if KeywordMatcher.any(query, ["foreldelse", "foreldet"]):
            if KeywordMatcher.any(query, ["reklamasjon", "reklamasjonsfrist"]):
                return RoutingDecision(route="OB-02", reason="Limitation reclamation rule")
            return RoutingDecision(route="DC-04", reason="Limitation debt rule")

        # Oppsigelse boundary
        if KeywordMatcher.any(query, ["si opp", "oppsigelsestid", "oppsigelsesklausul", "automatisk fornyelse"]):
            if KeywordMatcher.any(query, ["ansatt", "arbeidstaker", "arbeidsforhold", "arbeidsavtale", "oppsigelse av ansatt"]):
                return RoutingDecision(route="EL-02", reason="Employment termination rule")
            return RoutingDecision(route="OB-05", reason="Contract termination rule")

        # Insolvency boundary
        if KeywordMatcher.any(query, ["oppbud begjært", "konkurs åpnet", "bobestyrer", "slå konkurs", "begjære konkurs"]) or re.search(r"\bkonkursbo\b", q_lower):
            return RoutingDecision(route="IN-01", reason="Insolvency bankruptcy rule")

        return None

    @classmethod
    def get_metrics(cls) -> Dict[str, int]:
        return dict(cls._metrics)