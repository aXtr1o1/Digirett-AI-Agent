"""
router/confuser_resolver.py — Confuser Term Resolution Engine
"""

import logging
import re
from typing import Optional
from router.taxonomy_loader import taxonomy_loader
from router.utils.models import ResolvedRoute
from router.utils.stem_matcher import StemMatcher, Tokenizer

logger = logging.getLogger(__name__)


class ConfuserResolver:

    @staticmethod
    def resolve(subdomain_id: str, query_text: str) -> str:
        res = ConfuserResolver.resolve_detailed(subdomain_id, query_text)
        return res.route

    @staticmethod
    def resolve_detailed(subdomain_id: str, query_text: str) -> ResolvedRoute:
        sub_data = taxonomy_loader.get_subdomain(subdomain_id)
        if not sub_data:
            return ResolvedRoute(route=subdomain_id, reason="No taxonomy data")

        confusers = sub_data.get("confusers", [])
        if not confusers:
            return ResolvedRoute(route=subdomain_id, reason="No confusers configured")

        query_words = Tokenizer.tokenize(query_text)
        query_stems = StemMatcher.get_stems(query_words)

        for confuser in confusers:
            term = confuser.get("term", "").lower()
            if not term:
                continue

            clean_term = re.sub(r"\(.*?\)", "", term).strip()
            term_words = Tokenizer.tokenize(clean_term)
            term_stems = StemMatcher.get_stems(term_words)

            if term_stems and term_stems.issubset(query_stems):
                paren_match = re.search(r"\((.*?)\)", term)
                if paren_match:
                    paren_words = Tokenizer.tokenize(paren_match.group(1))
                    paren_stems = StemMatcher.get_stems(paren_words)
                    if paren_stems and not paren_stems.intersection(query_stems):
                        continue

                correct_route_str = confuser.get("correct_route", "")
                reason = confuser.get("reason", "Confuser rule hit")
                logger.info(
                    f"⚠️ Confuser hit: '{term}' matched query stems. "
                    f"Redirecting route from {subdomain_id} to '{correct_route_str}' | Reason: {reason}"
                )

                resolved_id = ConfuserResolver._parse_subdomain_id(correct_route_str)
                if resolved_id:
                    return ResolvedRoute(
                        route=resolved_id,
                        reason=reason,
                        matched_term=term,
                    )

        return ResolvedRoute(route=subdomain_id, reason="No confuser match")

    @staticmethod
    def _parse_subdomain_id(route_str: str) -> Optional[str]:
        if not route_str:
            return None
        match = re.search(r"\b([A-Z]{2}-\d{2})\b", route_str)
        if match:
            return match.group(1)

        parts = route_str.replace("/", " ").split()
        for p in parts:
            p_strip = p.strip().upper()
            if len(p_strip) == 5 and p_strip[2] == "-":
                return p_strip
        return None
