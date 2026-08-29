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
    logging.getLogger(__name__).warning(
        "rank_bm25 not installed — BM25 re-ranking disabled."
    )

logger = logging.getLogger(__name__)

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
        Apply Reciprocal Rank Fusion (RRF) combining dense vector rank and BM25.

        Legal retrieval uses document titles as first-class lexical evidence. The
        previous implementation indexed only chunk body text, so a query naming a
        regulation could lose to an unrelated body paragraph. Title fields are
        additive: if an older collection does not contain them, behavior falls
        back to the original text-only corpus.
        """
        if not results:
            return []

        if not _BM25_AVAILABLE or not raw_query:
            fallback_res: List[Dict[str, Any]] = []
            for r in results[:top_k]:
                c = r.copy()
                c["score_dense"] = round(float(r.get("score", 0.0)), 6)
                c["score_bm25"] = 0.0
                fallback_res.append(c)
            return fallback_res

        try:
            def tokenize_and_stem(text: str) -> List[str]:
                words = re.findall(r"\b\w{3,}\b", (text or "").lower())
                tokens: List[str] = []
                for w in words:
                    tokens.append(w[:10])
                    for root in [
                        "forlik",
                        "styre",
                        "konkurs",
                        "aksje",
                        "avtale",
                        "oppsig",
                        "kreditor",
                        "utlegg",
                        "pant",
                        "gebyr",
                        "forskrift",
                        "registr",
                        "arbeidsmiljo",
                        "overgang",
                        "ikraft",
                    ]:
                        if w.startswith(root) and w != root:
                            tokens.append(root[:10])
                return tokens

            def searchable_text(result: Dict[str, Any]) -> str:
                doc_title = str(
                    result.get("doc_title")
                    or result.get("law_title")
                    or ""
                )
                section_title = str(result.get("section_title") or "")
                citation = str(
                    result.get("citation_anchor")
                    or result.get("section_ref")
                    or ""
                )
                body = str(result.get("text") or "")

                # Repeat the document title once to give an explicit legal title
                # meaningful lexical weight without overwhelming section content.
                return " ".join(
                    part
                    for part in [
                        doc_title,
                        doc_title,
                        section_title,
                        citation,
                        body,
                    ]
                    if part
                )

            corpus = [searchable_text(r) for r in results]
            tok_c = [tokenize_and_stem(t) for t in corpus]
            tok_q = tokenize_and_stem(raw_query)

            bm25 = BM25Okapi(tok_c)
            bm25_scores = bm25.get_scores(tok_q)

            # Results are already sorted by dense relevance by RetrieverAgent.
            dense_ranked = {i: rank for rank, i in enumerate(range(len(results)))}
            bm25_ranked_idx = sorted(
                range(len(results)), key=lambda i: bm25_scores[i], reverse=True
            )
            bm25_rank_map = {
                idx: rank for rank, idx in enumerate(bm25_ranked_idx)
            }

            rrf = [
                (
                    i,
                    1 / (rrf_k + dense_ranked.get(i, len(results)))
                    + 1 / (rrf_k + bm25_rank_map.get(i, len(results))),
                )
                for i in range(len(results))
            ]

            boosted_rrf = []
            q_lower = raw_query.lower()
            q_words_clean = set(re.findall(r"\b\w{5,}\b", q_lower))
            section_matches_in_query = (
                re.findall(r"§\s*(\d+(?:-\d+)?)", q_lower)
                or re.findall(r"paragraf\s*(\d+(?:-\d+)?)", q_lower)
            )

            for i, rrf_val in rrf:
                r_doc = results[i]
                ref = r_doc.get("section_ref", "") or ""
                cleaned_ref = ref.replace("\xa0", " ").strip()
                cleaned_ref = re.sub(r"\s+", " ", cleaned_ref)
                if cleaned_ref and not cleaned_ref.startswith("§"):
                    cleaned_ref = "§ " + cleaned_ref

                boost = 0.0

                if section_matches_in_query and cleaned_ref:
                    for sec in section_matches_in_query:
                        if sec in cleaned_ref:
                            boost += 0.5
                            break

                combined_text_lower = searchable_text(r_doc).lower()
                if q_words_clean:
                    matches = sum(
                        1 for w in q_words_clean if w in combined_text_lower
                    )
                    match_ratio = matches / len(q_words_clean)
                    if match_ratio >= 0.5:
                        boost += 0.2 * match_ratio

                # Additional, bounded title overlap signal. It helps named-document
                # queries while remaining neutral when title metadata is absent.
                title_lower = str(
                    r_doc.get("doc_title") or r_doc.get("law_title") or ""
                ).lower()
                if title_lower and q_words_clean:
                    title_matches = sum(1 for w in q_words_clean if w in title_lower)
                    title_ratio = title_matches / len(q_words_clean)
                    if title_ratio >= 0.5:
                        boost += 0.25 * title_ratio

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
            logger.warning("BM25 rerank failed: %s — using dense-only", exc)
            fallback_res: List[Dict[str, Any]] = []
            for r in results[:top_k]:
                c = r.copy()
                c["score_dense"] = round(float(r.get("score", 0.0)), 6)
                c["score_bm25"] = 0.0
                fallback_res.append(c)
            return fallback_res
