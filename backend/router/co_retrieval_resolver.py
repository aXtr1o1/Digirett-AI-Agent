"""
router/co_retrieval_resolver.py — Modular Strategy Rule Engine for Co-Retrieval
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Set
from router.taxonomy_loader import taxonomy_loader
from router.utils.keyword_matcher import KeywordMatcher

logger = logging.getLogger(__name__)


class CoRetrievalRule(ABC):
    def __init__(self, priority: int = 10) -> None:
        self.priority = priority

    @abstractmethod
    def apply(self, sub_id: str, query_text: str, targets: Set[str]) -> None:
        pass


class BankruptcyRule(CoRetrievalRule):
    def apply(self, sub_id: str, query_text: str, targets: Set[str]) -> None:
        if sub_id == "IN-02" and KeywordMatcher.match(query_text, "dividende"):
            logger.info("🔗 Co-retrieval hit (BankruptcyRule): IN-02 + 'dividende' -> adding IN-03")
            targets.add("IN-03")
        if sub_id == "IN-03" and KeywordMatcher.any(query_text, ["krav", "melde", "anmelde"]):
            logger.info("🔗 Co-retrieval hit (BankruptcyRule): IN-03 + 'krav/melde' -> adding IN-02")
            targets.add("IN-02")


class CorporateRule(CoRetrievalRule):
    def apply(self, sub_id: str, query_text: str, targets: Set[str]) -> None:
        if sub_id == "CY-03" and KeywordMatcher.any(query_text, ["fortrinnsrett", "emisjon", "fravike", "fravikes", "generalforsamling"]):
            logger.info("🔗 Co-retrieval hit (CorporateRule): CY-03 + pre-emption -> adding CY-05")
            targets.add("CY-05")


class EmploymentBridgeRule(CoRetrievalRule):
    def apply(self, sub_id: str, query_text: str, targets: Set[str]) -> None:
        if sub_id == "OB-01":
            time_keywords = ["tid", "dager", "måneder", "år", "senere", "time", "days", "months", "years", "late", "sent"]
            if KeywordMatcher.any(query_text, time_keywords):
                logger.info("🔗 Co-retrieval hit (EmploymentBridgeRule): OB-01 + time element -> adding OB-02")
                targets.add("OB-02")

        if sub_id == "MA-03":
            logger.info("🔗 Co-retrieval hit (EmploymentBridgeRule): MA-03 pointer -> adding EL-04 and MA-01")
            targets.add("EL-04")
            targets.add("MA-01")

        if sub_id == "EL-04":
            logger.info("🔗 Co-retrieval hit (EmploymentBridgeRule): EL-04 -> adding MA-03 (Chapter 16 storage)")
            targets.add("MA-03")


class CoRetrievalResolver:
    _rules: List[CoRetrievalRule] = sorted(
        [BankruptcyRule(priority=1), CorporateRule(priority=2), EmploymentBridgeRule(priority=3)],
        key=lambda r: r.priority,
    )

    @classmethod
    def get_targets(cls, subdomain_ids: List[str], query_text: str) -> List[str]:
        final_targets: Set[str] = set()

        for sub_id in subdomain_ids:
            final_targets.add(sub_id)

            # 1. Dynamic JSON Taxonomy paired subdomains
            sub_data = taxonomy_loader.get_subdomain(sub_id)
            if sub_data:
                co_ret = sub_data.get("co_retrieval", {})
                if isinstance(co_ret, dict) and co_ret.get("paired_with"):
                    paired = co_ret["paired_with"]
                    logger.info(f"🔗 Co-retrieval match from JSON: subdomain '{sub_id}' paired with {paired}")
                    for p in paired:
                        final_targets.add(p)

            # 2. Strategy Rules
            for rule in cls._rules:
                rule.apply(sub_id, query_text, final_targets)

        return list(final_targets)
