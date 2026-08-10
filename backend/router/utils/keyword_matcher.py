"""
router/utils/keyword_matcher.py — Shared Token & Stem Keyword Matcher Utility
"""

from typing import Iterable, List
from router.query_normalizer import QueryNormalizer
from router.utils.stem_matcher import StemMatcher, Tokenizer


class KeywordMatcher:
    @staticmethod
    def match(text: str, keyword: str) -> bool:
        if not text or not keyword:
            return False
        q_norm = QueryNormalizer.clean_text(text)
        kw_norm = QueryNormalizer.clean_text(keyword)
        if kw_norm in q_norm:
            return True

        # Fallback to stem matching
        q_stems = StemMatcher.get_stems(Tokenizer.tokenize(text))
        kw_stems = StemMatcher.get_stems(Tokenizer.tokenize(keyword))
        return bool(kw_stems and kw_stems.issubset(q_stems))

    @classmethod
    def any(cls, text: str, keywords: Iterable[str]) -> bool:
        if not text or not keywords:
            return False
        return any(cls.match(text, kw) for kw in keywords)
