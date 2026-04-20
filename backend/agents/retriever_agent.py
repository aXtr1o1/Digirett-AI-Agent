"""
agents/retriever_agent.py

Retrieval Agent — 4-Level Statute-Anchored Fallback + BM25 Re-ranking.

Replaces the old RetrieverAgent (single Milvus call) and RerankerAgent
(LLM-based scoring) with:

  L0  source_doc_url + domain + subdomain + jurisdiction + b2b_b2c
  L1  source_doc_url + domain
  L2  source_doc_url only
  L3  no filter — pure vector search

BM25 re-ranking (RRF fusion) is applied on the candidate set before
returning top_k results.  No LLM call needed for reranking.

The RerankerAgent class is kept in its own file and still exists —
it is simply no longer called from the legal pipeline.  This avoids
any import errors in other parts of the codebase.
"""

import logging
from typing import Any, Dict, List, Optional

try:
    from rank_bm25 import BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "rank_bm25 not installed — BM25 re-ranking disabled. "
        "pip install rank-bm25"
    )

logger = logging.getLogger(__name__)

# How many candidates to fetch before re-ranking (top_k × OVERFETCH_FACTOR)
_OVERFETCH_FACTOR = 4

# Anti-hallucination text returned when all 4 levels return 0 results
_ANTI_HALLUCINATION_TEXT = (
    "DigiRett AI kan ikke bekrefte et svar fra autoriserte kilder for dette spørsmålet. "
    "Vennligst kontakt en kvalifisert advokat for veiledning om dette rettslige spørsmålet."
)


class _BM25Reranker:
    """
    Reciprocal Rank Fusion of dense COSINE score + BM25 score.
    Falls back to dense-only when rank_bm25 is not installed.
    """

    _K = 60  # RRF constant

    @classmethod
    def rerank(
        cls,
        results: List[Dict[str, Any]],
        raw_query: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        if not results:
            return []

        if not _BM25_AVAILABLE or not raw_query:
            return results[:top_k]

        try:
            corpus = [r.get("text", "") or "" for r in results]
            tok_c = [t.lower().split() for t in corpus]
            tok_q = raw_query.lower().split()

            bm25 = BM25Okapi(tok_c)
            bm25_scores = bm25.get_scores(tok_q)

            # Dense rank (by position in results list — already sorted by COSINE)
            dense_ranked = {i: rank for rank, i in enumerate(range(len(results)))}
            # BM25 rank
            bm25_ranked_idx = sorted(
                range(len(results)), key=lambda i: bm25_scores[i], reverse=True
            )
            bm25_rank_map = {idx: rank for rank, idx in enumerate(bm25_ranked_idx)}

            rrf = [
                (
                    i,
                    1 / (cls._K + dense_ranked.get(i, len(results)))
                    + 1 / (cls._K + bm25_rank_map.get(i, len(results))),
                )
                for i in range(len(results))
            ]
            rrf.sort(key=lambda x: x[1], reverse=True)

            reranked = []
            for i, rrf_val in rrf[:top_k]:
                r = results[i].copy()
                r["score"] = round(rrf_val, 6)
                r["score_dense"] = round(float(results[i].get("score", 0.0)), 6)
                r["score_bm25"] = round(float(bm25_scores[i]), 4)
                reranked.append(r)

            return reranked

        except Exception as exc:
            logger.warning(f"⚠️  BM25 rerank failed: {exc} — using dense-only")
            return results[:top_k]


class RetrieverAgent:
    """
    Orchestrates the full retrieval pipeline:

      1. Embed the enriched query
      2. Run 4-level fallback ladder against Milvus
      3. BM25 re-rank the candidate set
      4. Return top_k results

    Constructor signature is unchanged — embedding_service and milvus_client
    are injected from RAGService exactly as before.
    """

    def __init__(self, embedding_service: Any, milvus_client: Any) -> None:
        self._embedding = embedding_service
        self._milvus = milvus_client
        logger.info("✅ RetrieverAgent initialized (v3 — 4-level fallback + BM25)")

    async def run(
        self,
        query: str,
        enriched_query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        history: Optional[List[Dict[str, str]]] = None,
        # New metadata filters from QueryReasoningAgent + RouterAgent
        statute_filter: Optional[str] = None,      # Lovdata URL or LOV-YYYY-MM-DD-NNN
        domain: Optional[str] = None,              # e.g. "selskapsrett"
        jurisdiction: Optional[str] = None,        # e.g. "NO"
        subdomain_candidates: Optional[List[str]] = None,
        b2b_b2c: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run the full retrieval pipeline and return re-ranked results.

        Parameters
        ----------
        query           : raw user query (used for BM25 scoring)
        enriched_query  : statute-anchored query from QueryReasoningAgent (used for embedding)
        top_k           : number of results to return after re-ranking
        statute_filter  : Lovdata URL or LOV-ID used for source_doc_url LIKE filter
        domain          : Milvus `domain` field value
        jurisdiction    : Milvus `jurisdiction` field value
        subdomain_candidates : list of subdomain label strings from RouterAgent
        b2b_b2c         : "B2B" / "B2C" / "BOTH"

        Returns
        -------
        List of result dicts, each containing at minimum:
            text, score, score_dense, score_bm25,
            source_doc_url, section_ref, url (alias for source_doc_url),
            domain, subdomain, chunk_id, document_id,
            fallback_level
        """
        sep = "=" * 60
        logger.info(
            f"\n{sep}\n🔍 RetrieverAgent.run | query='{query[:60]}'\n{sep}"
        )
        logger.info(f"  Enriched query  : {enriched_query[:100]}")
        logger.info(f"  statute_filter  : {statute_filter}")
        logger.info(f"  domain          : {domain}")
        logger.info(f"  jurisdiction    : {jurisdiction}")
        logger.info(f"  subdomain_cands : {subdomain_candidates}")
        logger.info(f"  b2b_b2c         : {b2b_b2c}")

        # ── 1. Embed enriched query ────────────────────────────────────────
        query_embedding = await self._embedding.embed_query(enriched_query)
        logger.debug(f"  Embedding dim   : {len(query_embedding)}")

        fetch_k = top_k * _OVERFETCH_FACTOR
        candidates: List[Dict[str, Any]] = []
        fallback_level = 0

        # ── 2. 4-Level fallback ladder ─────────────────────────────────────
        logger.info("[Fallback] Starting L0…")

        # L0 — tightest: statute + domain + subdomain + jurisdiction + b2b
        candidates = self._milvus_search(
            query_embedding=query_embedding,
            top_k=fetch_k,
            statute_filter=statute_filter,
            domain=domain,
            jurisdiction=jurisdiction,
            subdomain_candidates=subdomain_candidates,
            b2b_b2c=b2b_b2c,
            fallback_level=0,
        )
        logger.info(f"  L0 → {len(candidates)} candidates")

        if not candidates:
            fallback_level = 1
            logger.info("[Fallback] L0 empty → trying L1 (statute + domain)…")
            candidates = self._milvus_search(
                query_embedding=query_embedding,
                top_k=fetch_k,
                statute_filter=statute_filter,
                domain=domain,
                jurisdiction=jurisdiction,
                subdomain_candidates=None,
                b2b_b2c=None,
                fallback_level=1,
            )
            logger.info(f"  L1 → {len(candidates)} candidates")

        if not candidates:
            fallback_level = 2
            logger.info("[Fallback] L1 empty → trying L2 (statute only)…")
            candidates = self._milvus_search(
                query_embedding=query_embedding,
                top_k=fetch_k,
                statute_filter=statute_filter,
                domain=None,
                jurisdiction=None,
                subdomain_candidates=None,
                b2b_b2c=None,
                fallback_level=2,
            )
            logger.info(f"  L2 → {len(candidates)} candidates")

        if not candidates:
            fallback_level = 3
            logger.info("[Fallback] L2 empty → trying L3 (no filter, pure vector)…")
            candidates = self._milvus_search(
                query_embedding=query_embedding,
                top_k=fetch_k,
                statute_filter=None,
                domain=None,
                jurisdiction=None,
                subdomain_candidates=None,
                b2b_b2c=None,
                fallback_level=3,
            )
            logger.info(f"  L3 → {len(candidates)} candidates")

        if not candidates:
            logger.warning(
                "⚠️  All 4 fallback levels returned 0 results. "
                "Collection may be empty or query is fully out of domain."
            )
            return []

        # ── 3. BM25 re-rank ───────────────────────────────────────────────
        logger.info(
            f"[BM25] Re-ranking {len(candidates)} candidates → top {top_k} "
            f"(BM25: {'on' if _BM25_AVAILABLE else 'off'})…"
        )
        reranked = _BM25Reranker.rerank(
            results=candidates,
            raw_query=query,
            top_k=top_k,
        )

        # ── 4. Annotate with fallback level ────────────────────────────────
        for r in reranked:
            r["fallback_level"] = fallback_level

        logger.info(
            f"✅ RetrieverAgent done | {len(reranked)} results | "
            f"fallback=L{fallback_level} | statute={statute_filter or 'none'}"
        )
        for i, r in enumerate(reranked[:3], 1):
            logger.info(
                f"  [{i}] score={r.get('score', 0):.5f} | "
                f"domain={r.get('domain')} | subdomain={r.get('subdomain')} | "
                f"section_ref={r.get('section_ref')}"
            )

        return reranked

    # ── Internal ──────────────────────────────────────────────────────────

    def _milvus_search(
        self,
        query_embedding: List[float],
        top_k: int,
        statute_filter: Optional[str],
        domain: Optional[str],
        jurisdiction: Optional[str],
        subdomain_candidates: Optional[List[str]],
        b2b_b2c: Optional[str],
        fallback_level: int,
    ) -> List[Dict[str, Any]]:
        """Thin wrapper — delegates all filter logic to MilvusClient."""
        try:
            return self._milvus.search(
                embedding=query_embedding,
                metric_type="COSINE",
                top_k=top_k,
                statute_filter=statute_filter,
                domain=domain,
                jurisdiction=jurisdiction,
                subdomain_candidates=subdomain_candidates,
                b2b_b2c=b2b_b2c,
                fallback_level=fallback_level,
            )
        except Exception as exc:
            logger.error(f"❌ Milvus search (L{fallback_level}) failed: {exc}")
            return []