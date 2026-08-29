"""
router/keyword_scorer.py — Strategy-Based Keyword Scorer Component
"""

import os
import difflib
from typing import Dict, List, Set, Tuple
from router.query_normalizer import QueryNormalizer
from router.taxonomy_loader import taxonomy_loader

# Configurable scoring weights
SCORING_WEIGHTS = {
    "phrase_match": 1.5,
    "token_match_scale": 0.5,
    "low_conf_multiplier": 0.4,
}

_STOPWORDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "language",
    "norwegian_stopwords.txt",
)

def _load_stopwords() -> Set[str]:
    stopwords = set()
    if os.path.exists(_STOPWORDS_PATH):
        try:
            with open(_STOPWORDS_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip().lower()
                    if w and not w.startswith("#"):
                        stopwords.add(w)
        except Exception:
            pass
    if not stopwords:
        stopwords = {"og", "i", "jeg", "det", "at", "en", "et", "den", "til", "er", "som", "på", "de", "med", "for", "hva", "hvordan"}
    return stopwords

STOP_WORDS = _load_stopwords()


class PhraseScorer:
    @staticmethod
    def score(clean_kw_str: str, clean_query_str: str) -> float:
        if clean_kw_str and clean_kw_str in clean_query_str:
            return SCORING_WEIGHTS["phrase_match"]
        return 0.0


class TokenScorer:
    @staticmethod
    def score(kw_tokens: Set[str], query_tokens: Set[str]) -> float:
        kw_filtered = kw_tokens - STOP_WORDS
        query_filtered = query_tokens - STOP_WORDS
        if not kw_filtered:
            return 0.0
        matching = kw_filtered.intersection(query_filtered)
        if matching:
            return (len(matching) / len(kw_filtered)) * SCORING_WEIGHTS["token_match_scale"]
        
        # Fuzzy fallback token scoring
        fuzzy_matches = 0
        for kw_t in kw_filtered:
            if len(kw_t) > 4:
                close = difflib.get_close_matches(kw_t, list(query_filtered), n=1, cutoff=0.85)
                if close:
                    fuzzy_matches += 1
        if fuzzy_matches > 0:
            return (fuzzy_matches / len(kw_filtered)) * SCORING_WEIGHTS["token_match_scale"] * 0.8
        return 0.0


class KeywordScorer:
    @classmethod
    def score_query(cls, query_text: str, key_concepts: List[str] = None) -> List[Tuple[str, float]]:
        if not query_text:
            return []

        normalized_query_tokens = QueryNormalizer.normalize(query_text)
        clean_query_str = " ".join(normalized_query_tokens)

        concept_tokens = []
        if key_concepts:
            for concept in key_concepts:
                concept_tokens.extend(QueryNormalizer.normalize(concept))

        all_query_tokens = set(normalized_query_tokens + concept_tokens)
        subdomains = taxonomy_loader.get_all_subdomains()
        scores: Dict[str, float] = {}

        for sub_id, sub_data in subdomains.items():
            keywords = sub_data.get("routing_keywords", [])
            if not keywords:
                continue

            sub_score = 0.0
            for keyword in keywords:
                keyword_lower = keyword.lower()
                keyword_tokens = QueryNormalizer.normalize(keyword_lower)
                if len(keyword_tokens) > 1:
                    clean_kw_str = " ".join(keyword_tokens)
                    p_score = PhraseScorer.score(clean_kw_str, clean_query_str)
                    if p_score > 0:
                        sub_score += p_score
                        continue

                t_score = TokenScorer.score(set(keyword_tokens), all_query_tokens)
                sub_score += t_score

            if sub_score > 0:
                scores[sub_id] = sub_score

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        if not sorted_scores:
            return []

        max_score = sorted_scores[0][1]
        top_confidence = max_score * SCORING_WEIGHTS["low_conf_multiplier"] if max_score < 1.0 else min(max_score / 3.0, 1.0)
        return [(sub_id, top_confidence if idx == 0 else top_confidence * 0.8) for idx, (sub_id, s) in enumerate(sorted_scores)]
