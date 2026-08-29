"""
router/utils/stem_matcher.py — Fast Suffix Stemming & Tokenizer Utility
"""

import re
from typing import List, Set


class Tokenizer:
    WORD_PATTERN = re.compile(r"\b\w{3,}\b")

    @classmethod
    def tokenize(cls, text: str) -> List[str]:
        if not text:
            return []
        return cls.WORD_PATTERN.findall(text.lower())


class StemMatcher:
    @staticmethod
    def get_stem(word: str) -> str:
        if not word:
            return ""
        w = word.lower()
        if len(w) <= 5:
            return w
        # Fast Norwegian suffix stripping
        for suffix in ("ingene", "ingens", "ingam", "elsen", "elser", "heten", "heter", "ingen", "inger", "enes", "ene", "ens", "ers"):
            if w.endswith(suffix) and len(w) - len(suffix) >= 4:
                return w[:-len(suffix)]
        if len(w) > 9:
            return w[:9]
        return w

    @classmethod
    def get_stems(cls, words: List[str]) -> Set[str]:
        return {cls.get_stem(w) for w in words if w}
