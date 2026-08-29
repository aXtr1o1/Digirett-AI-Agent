"""
router/query_normalizer.py — Optimized Query Normalization Utility
"""

import re
import unicodedata
from typing import List

CLEAN_PATTERN = re.compile(r"[^\w\s\-\u00E6\u00F8\u00E5\u00C6\u00D8\u00C5]")
MULTIPLE_SPACES_PATTERN = re.compile(r"\s+")


class QueryNormalizer:

    @staticmethod
    def normalize(text: str, stem: bool = False, remove_punctuation: bool = True) -> List[str]:
        if not text:
            return []

        # 1. Unicode NFC Normalization
        normalized = unicodedata.normalize("NFC", text.lower())

        # 2. Clean punctuation
        if remove_punctuation:
            normalized = CLEAN_PATTERN.sub(" ", normalized)

        # 3. Collapse multiple whitespace
        normalized = MULTIPLE_SPACES_PATTERN.sub(" ", normalized).strip()

        tokens = [t.strip() for t in normalized.split() if t.strip()]
        if stem:
            from router.utils.stem_matcher import StemMatcher
            return [StemMatcher.get_stem(t) for t in tokens]
        return tokens

    @classmethod
    def clean_text(cls, text: str) -> str:
        if not text:
            return ""
        return " ".join(cls.normalize(text))
