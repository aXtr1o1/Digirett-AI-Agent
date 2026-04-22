"""
agents/retriever_agent.py

RetrieverAgent — v5 (smart statute_explicit + registry-aware fallback).

Key changes from v4:
─────────────────────────────────────────────────────────────────────
1. statute_from_registry parameter (NEW):
   - True  → statute ID came from StatuteRegistry (deterministic).
              Hard-block fallback if statute exhausted (safe — we know the ID is correct).
   - False → statute ID came from LLM inference (unreliable).
              Never hard-block: always allow domain fallback (L3) and pure-vector (L4).

2. _is_statute_explicit() is no longer the sole guard.
   It still detects "Lov om" in queries (for logging/metrics) but does NOT
   control the hard-block alone — only statute_from_registry does that.

3. Fallback ladder unchanged (L0→L1→L2→L3→L4) but:
   - LLM-inferred statutes: if L0-L2 return 0 results → continue to L3/L4
   - Registry statutes:     if L0-L2 return 0 results → stop (correct statute not in VDB)
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


class _BM25Reranker:
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

            dense_ranked = {i: rank for rank, i in enumerate(range(len(results)))}
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

            reranked: List[Dict[str, Any]] = []
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
    def __init__(self, embedding_service: Any, milvus_client: Any) -> None:
        self._embedding = embedding_service
        self._milvus = milvus_client
        logger.info(
            "✅ RetrieverAgent initialized "
            "(v5 — registry-aware statute blocking + BM25)"
        )

    async def run(
        self,
        query: str,
        enriched_query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        history: Optional[List[Dict[str, str]]] = None,
        statute_filter: Optional[str] = None,
        domain: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        subdomain_candidates: Optional[List[str]] = None,
        b2b_b2c: Optional[str] = None,
        # ── NEW parameter ───────────────────────────────────────────────
        statute_from_registry: bool = False,
        # ── KEPT for backward compat but no longer controls hard-block ──
        statute_explicit: bool = False,
    ) -> List[Dict[str, Any]]:
        sep = "=" * 60
        logger.info(f"\n{sep}\n🔍 RetrieverAgent.run | query='{query[:60]}'\n{sep}")
        logger.info(f"  Enriched query      : {enriched_query[:100]}")
        logger.info(f"  statute_filter      : {statute_filter}")
        logger.info(f"  statute_from_registry: {statute_from_registry}")
        logger.info(f"  domain              : {domain}")
        logger.info(f"  jurisdiction        : {jurisdiction}")
        logger.info(f"  subdomain_cands     : {subdomain_candidates}")
        logger.info(f"  b2b_b2c             : {b2b_b2c}")

        query_embedding = await self._embedding.embed_query(enriched_query)
        logger.debug(f"  Embedding dim       : {len(query_embedding)}")

        fetch_k = top_k * _OVERFETCH_FACTOR
        candidates: List[Dict[str, Any]] = []
        fallback_level = 0

        # ── L0: statute + domain + subdomain + jurisdiction + b2b ──────────
        logger.info("[Fallback] Starting L0…")
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
                jurisdiction=None,
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

        # ── CRITICAL GATE: only hard-block when statute ID is CERTAIN ──────
        # If the statute came from the deterministic registry, we KNOW the ID
        # is correct. If the VDB has no chunks for it, there is nothing to
        # return — falling through to L3/L4 would retrieve wrong-statute content.
        #
        # If the statute came from LLM inference, the ID may be wrong.
        # Always fall through to domain-level search so the user gets
        # some answer rather than empty context.
        if not candidates and statute_filter:
            if statute_from_registry:
                logger.warning(
                    "⚠️  Registry statute exhausted L0-L2. "
                    "Statute is confirmed correct but NOT in VDB. "
                    "Stopping retrieval — wrong-statute drift would harm accuracy."
                )
                return []
            else:
                logger.info(
                    "ℹ️  LLM-inferred statute exhausted L0-L2. "
                    "Statute ID may be wrong — continuing to domain-level fallback."
                )

        if not candidates:
            fallback_level = 3
            logger.info("[Fallback] → trying L3 (domain + subdomain, NO statute)…")
            candidates = self._milvus_search(
                query_embedding=query_embedding,
                top_k=fetch_k,
                statute_filter=None,
                domain=domain,
                jurisdiction=jurisdiction,
                subdomain_candidates=subdomain_candidates,
                b2b_b2c=b2b_b2c,
                fallback_level=3,
            )
            logger.info(f"  L3 → {len(candidates)} candidates")

        if not candidates:
            fallback_level = 4
            logger.info("[Fallback] L3 empty → trying L4 (pure vector, no filters)…")
            candidates = self._milvus_search(
                query_embedding=query_embedding,
                top_k=fetch_k,
                statute_filter=None,
                domain=None,
                jurisdiction=None,
                subdomain_candidates=None,
                b2b_b2c=None,
                fallback_level=4,
            )
            logger.info(f"  L4 → {len(candidates)} candidates")

        if not candidates:
            logger.warning(
                "⚠️  All 5 fallback levels returned 0 results. "
                "Collection may be empty or query is fully out of domain."
            )
            return []

        logger.info(
            f"[BM25] Re-ranking {len(candidates)} candidates → top {top_k} "
            f"(BM25: {'on' if _BM25_AVAILABLE else 'off'})…"
        )
        reranked = _BM25Reranker.rerank(results=candidates, raw_query=query, top_k=top_k)

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