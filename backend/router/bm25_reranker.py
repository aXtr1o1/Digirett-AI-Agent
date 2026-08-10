"""
router/bm25_reranker.py — Independent BM25 & Reciprocal Rank Fusion (RRF) Reranker
"""

import logging
import re
from typing import Any, Dict, List

try:
    from rank_bm25 import BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False
    logging.getLogger(__name__).warning("rank_bm25 not installed — BM25 re-ranking disabled.")

logger = logging.getLogger(__name__)

# ── NAMED CONSTANTS ──────────────────────────────────────────────────
RRF_K_CONSTANT = 60


class BM25Reranker:

    @classmethod
    def rerank(
        cls,
        results: List[Dict[str, Any]],
        raw_query: str,
        top_k: int = 5,
        rrf_k: int = RRF_K_CONSTANT,
    ) -> List[Dict[str, Any]]:
        """
        Applies Reciprocal Rank Fusion (RRF) combining dense vector rank and BM25 lexically boosted rank.
        """
        if not results:
            return []

        if not _BM25_AVAILABLE or not raw_query:
            fallback_res = []
            for r in results[:top_k]:
                c = r.copy()
                c["score_dense"] = round(float(r.get("score", 0.0)), 6)
                c["score_bm25"] = 0.0
                fallback_res.append(c)
            return fallback_res


        try:
            def tokenize_and_stem(text: str) -> List[str]:
                words = re.findall(r"\b\w{3,}\b", text.lower())
                tokens = []
                for w in words:
                    tokens.append(w[:10])
                    for root in ["forlik", "styre", "konkurs", "aksje", "avtale", "oppsig", "kreditor", "utlegg", "pant", "gebyr"]:
                        if w.startswith(root) and w != root:
                            tokens.append(root)
                return tokens

            corpus = [r.get("text", "") or "" for r in results]
            tok_c = [tokenize_and_stem(t) for t in corpus]
            tok_q = tokenize_and_stem(raw_query)

            bm25 = BM25Okapi(tok_c)
            bm25_scores = bm25.get_scores(tok_q)

            dense_ranked = {i: rank for rank, i in enumerate(range(len(results)))}
            bm25_ranked_idx = sorted(range(len(results)), key=lambda i: bm25_scores[i], reverse=True)
            bm25_rank_map = {idx: rank for rank, idx in enumerate(bm25_ranked_idx)}

            rrf = [
                (
                    i,
                    1 / (rrf_k + dense_ranked.get(i, len(results)))
                    + 1 / (rrf_k + bm25_rank_map.get(i, len(results))),
                )
                for i in range(len(results))
            ]

            # Dynamic Golden Section Match Boosters
            boosted_rrf = []
            for i, rrf_val in rrf:
                r_doc = results[i]
                ref = r_doc.get("section_ref", "") or ""
                cleaned_ref = ref.replace("\xa0", " ").strip()
                cleaned_ref = re.sub(r"\s+", " ", cleaned_ref)
                if cleaned_ref and not cleaned_ref.startswith("§"):
                    cleaned_ref = "§ " + cleaned_ref

                q_lower = raw_query.lower()
                boost = 0.0

                section_matches_in_query = re.findall(r"§\s*(\d+(?:-\d+)?)", q_lower) or re.findall(r"paragraf\s*(\d+(?:-\d+)?)", q_lower)
                if section_matches_in_query and cleaned_ref:
                    for sec in section_matches_in_query:
                        if sec in cleaned_ref:
                            boost += 0.5
                            break

                doc_text_lower = (r_doc.get("text", "") or "").lower()
                q_words_clean = set(re.findall(r"\b\w{5,}\b", q_lower))
                if q_words_clean:
                    matches = sum(1 for w in q_words_clean if w in doc_text_lower)
                    match_ratio = matches / len(q_words_clean)
                    if match_ratio >= 0.5:
                        boost += 0.2 * match_ratio

                boosted_rrf.append((i, rrf_val + boost))

            boosted_rrf.sort(key=lambda x: x[1], reverse=True)

            reranked: List[Dict[str, Any]] = []
            for i, rrf_val in boosted_rrf[:top_k]:
                r = results[i].copy()
                r["score"] = round(rrf_val, 6)
                r["score_dense"] = round(float(results[i].get("score", 0.0)), 6)
                r["score_bm25"] = round(float(bm25_scores[i]), 4)
                reranked.append(r)

            return reranked

        except Exception as exc:
            logger.warning(f" BM25 rerank failed: {exc} — using dense-only")
            fallback_res = []
            for r in results[:top_k]:
                c = r.copy()
                c["score_dense"] = round(float(r.get("score", 0.0)), 6)
                c["score_bm25"] = 0.0
                fallback_res.append(c)
            return fallback_res

