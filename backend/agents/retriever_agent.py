"""
agents/retriever_agent.py — Legal Vector & Statute Retriever Agent

Refactored per TL Code Review Guidelines:
1. Independent BM25 Reranker module (router.bm25_reranker.BM25Reranker).
2. DRY strategy loop for fallbacks (L0 -> L1 -> L2 -> L3 -> L4).
3. Config-driven penalty map (FALLBACK_PENALTIES).
4. Centralized OVERFETCH_FACTOR = 6 and RRF_K_CONSTANT = 60 constants.
5. Typed RetrievedChunk Pydantic model schema.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from router.bm25_reranker import BM25Reranker, RRF_K_CONSTANT

logger = logging.getLogger(__name__)

# ── NAMED CONSTANTS ──────────────────────────────────────────────────
OVERFETCH_FACTOR = 6

FALLBACK_PENALTIES: Dict[int, float] = {
    0: 1.0,
    1: 0.9,
    2: 0.8,
    3: 0.7,
    4: 0.5,
}


class RetrievedChunk(BaseModel):
    text: str = Field(default="")
    score: float = Field(default=0.0)
    score_dense: float = Field(default=0.0)
    score_bm25: float = Field(default=0.0)
    source_doc_url: str = Field(default="")
    section_ref: str = Field(default="")
    url: str = Field(default="")
    domain: str = Field(default="")
    subdomain: str = Field(default="")
    chunk_id: str = Field(default="")
    document_id: str = Field(default="")
    fallback_level: int = Field(default=0)


class RetrieverAgent:
    def __init__(self, embedding_service: Any, milvus_client: Any) -> None:
        self._embedding = embedding_service
        self._milvus = milvus_client
        logger.info("[OK] RetrieverAgent initialized")

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
        statute_from_registry: bool = False,
        statute_explicit: bool = False,
    ) -> List[Dict[str, Any]]:
        
        query_embedding = await self._embedding.embed_query(enriched_query)
        fetch_k = top_k * OVERFETCH_FACTOR
        candidates: List[Dict[str, Any]] = []
        effective_fallback_level = 0

        # Define fallback strategy search configurations
        strategies = [
            # L0: statute + domain + subdomain + jurisdiction + b2b
            {"level": 0, "statute": statute_filter, "domain": domain, "jurisdiction": jurisdiction, "subdomains": subdomain_candidates, "b2b": b2b_b2c},
            # L1: statute + domain
            {"level": 1, "statute": statute_filter, "domain": domain, "jurisdiction": None, "subdomains": None, "b2b": None},
            # L2: statute only
            {"level": 2, "statute": statute_filter, "domain": None, "jurisdiction": None, "subdomains": None, "b2b": None},
            # L3: domain + subdomain + jurisdiction + b2b
            {"level": 3, "statute": None, "domain": domain, "jurisdiction": jurisdiction, "subdomains": subdomain_candidates, "b2b": b2b_b2c},
            # L4: domain only
            {"level": 4, "statute": None, "domain": domain, "jurisdiction": None, "subdomains": None, "b2b": None},
        ]

        for strat in strategies:
            # Skip statute search if no statute_filter provided
            if strat["level"] in (0, 1, 2) and not statute_filter:
                continue

            results = self._milvus_search(
                query_embedding=query_embedding,
                top_k=fetch_k,
                statute_filter=strat["statute"],
                domain=strat["domain"],
                jurisdiction=strat["jurisdiction"],
                subdomain_candidates=strat["subdomains"],
                b2b_b2c=strat["b2b"],
                fallback_level=strat["level"],
            )

            # Target statute guard check for L0
            if strat["level"] == 0 and results and statute_filter:
                match = re.search(r"(\d{4}-\d{2}-\d{2}-\d+)", statute_filter)
                if match:
                    statute_id = match.group(1)
                    allowed_statutes = [statute_id]
                    from router.taxonomy_loader import taxonomy_loader
                    if subdomain_candidates:
                        for sub_id in subdomain_candidates:
                            sub_data = taxonomy_loader.get_subdomain(sub_id)
                            if sub_data:
                                for src in sub_data.get("required_sources", []):
                                    sid = src.get("source_id")
                                    if sid:
                                        dp = re.sub(r"^(LOV|FOR|FORSKRIFT)-", "", sid, flags=re.IGNORECASE)
                                        if dp and dp not in allowed_statutes:
                                            allowed_statutes.append(dp)

                    has_target = any(
                        any(allowed_id in (c.get("source_doc_url") or "") for allowed_id in allowed_statutes)
                        for c in results
                    )
                    if not has_target:
                        results = []

            if results:
                candidates = results
                effective_fallback_level = strat["level"]
                break

        if not candidates:
            logger.warning(f"RetrieverAgent: 0 candidates found across fallbacks for query '{query[:40]}'")
            return []

        # Delegate BM25 re-ranking to independent BM25Reranker module
        reranked = BM25Reranker.rerank(
            results=candidates,
            raw_query=query,
            top_k=top_k,
            rrf_k=RRF_K_CONSTANT,
        )

        # Apply config-driven fallback penalties
        penalty = FALLBACK_PENALTIES.get(effective_fallback_level, 0.5)
        final_results: List[Dict[str, Any]] = []

        for item in reranked:
            item["fallback_level"] = effective_fallback_level
            if penalty < 1.0 and "score" in item:
                item["score"] = round(float(item["score"]) * penalty, 6)

            # Validate schema via RetrievedChunk Pydantic model
            chunk_obj = RetrievedChunk(
                text=str(item.get("text", "")),
                score=float(item.get("score", 0.0)),
                score_dense=float(item.get("score_dense", 0.0)),
                score_bm25=float(item.get("score_bm25", 0.0)),
                source_doc_url=str(item.get("source_doc_url", "") or item.get("url", "")),
                section_ref=str(item.get("section_ref", "")),
                url=str(item.get("url", "") or item.get("source_doc_url", "")),
                domain=str(item.get("domain", "")),
                subdomain=str(item.get("subdomain", "")),
                chunk_id=str(item.get("chunk_id", "")),
                document_id=str(item.get("document_id", "")),
                fallback_level=int(effective_fallback_level),
            )
            final_results.append(chunk_obj.model_dump())

        return final_results

    def _milvus_search(
        self,
        query_embedding: List[float],
        top_k: int,
        statute_filter: Optional[str] = None,
        domain: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        subdomain_candidates: Optional[List[str]] = None,
        b2b_b2c: Optional[str] = None,
        fallback_level: int = 0,
    ) -> List[Dict[str, Any]]:
        """Invokes underlying Milvus search client."""
        try:
            return self._milvus.search(
                embedding=query_embedding,
                top_k=top_k,
                statute_filter=statute_filter,
                domain=domain,
                jurisdiction=jurisdiction,
                subdomain_candidates=subdomain_candidates,
                b2b_b2c=b2b_b2c,
                fallback_level=fallback_level,
            )
        except Exception as exc:

            logger.error(f"❌ Milvus search level L{fallback_level} failed: {exc}")
            return []