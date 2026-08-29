"""
agents/retriever_agent.py

Document-first multi-channel legal retrieval.

Public API compatibility:
    RetrieverAgent(...).run(...) -> List[chunk dict]

The surrounding RAG pipeline does not need to change.

Architecture:
1. Embed the enriched query once.
2. Discover legal DOCUMENTS through independent channels:
   - exact/fuzzy title
   - title BM25
   - statute ANN
   - routed subdomain ANN
   - domain ANN
   - broad ANN
3. Fuse/dedupe by canonical_document_id.
4. Search/rank chunks only inside the top legal documents.
5. Return the same chunk-shaped dictionaries expected by RAGService.

No channel is allowed to make another channel impossible.
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from agents.document_candidate_ranker import DocumentCandidateRanker
from agents.document_search_backend import DocumentSearchBackend
from agents.document_title_resolver import DocumentTitleResolver
from router.bm25_reranker import BM25Reranker, RRF_K_CONSTANT

logger = logging.getLogger(__name__)


TITLE_DOCUMENT_LIMIT = 20
MIN_DOCUMENT_CANDIDATES = 8
MAX_DOCUMENT_CANDIDATES = 15

SUBDOMAIN_MIN_CHUNK_K = 120
DOMAIN_MIN_CHUNK_K = 300
BROAD_MIN_CHUNK_K = 500
STATUTE_MIN_CHUNK_K = 160
SELECTED_DOC_MIN_CHUNK_K = 160

SUBDOMAIN_MAX_CHUNK_K = 240
DOMAIN_MAX_CHUNK_K = 500
BROAD_MAX_CHUNK_K = 800
SELECTED_DOC_MAX_CHUNK_K = 320

SEED_CHUNKS_PER_DOC_PER_CHANNEL = 4
EMBED_CACHE_SECONDS = 20.0
CHANNEL_CACHE_SECONDS = 20.0

# Final document -> chunk selection policy.
#
# These constants affect ONLY the last selection stage after document discovery
# and document ranking are already complete.
TOP_DOCUMENT_MIN_RESERVED_CHUNKS = 1
TOP_DOCUMENT_LOCAL_RERANK_LIMIT = 8


class RetrievedChunk(BaseModel):
    # Existing fields
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

    # Additive metadata. Existing downstream consumers may ignore these.
    source_url: str = Field(default="")
    doc_title: str = Field(default="")
    canonical_document_id: str = Field(default="")
    document_rank: int = Field(default=0)
    document_score: float = Field(default=0.0)
    retrieval_mode: str = Field(default="multichannel_document_first")
    retrieval_channels: List[Dict[str, Any]] = Field(default_factory=list)


def _doc_id(row: Dict[str, Any]) -> str:
    return str(
        row.get("canonical_document_id")
        or row.get("document_id")
        or ""
    ).strip()


def _chunk_key(row: Dict[str, Any]) -> str:
    cid = str(row.get("chunk_id") or "").strip()
    if cid:
        return cid
    return "|".join(
        [
            _doc_id(row),
            str(row.get("section_ref") or row.get("section_number") or ""),
            str(row.get("source_url") or row.get("url") or ""),
            str(row.get("text") or "")[:120],
        ]
    )


def _unique_docs_from_chunks(
    rows: Sequence[Dict[str, Any]],
    *,
    max_docs: Optional[int] = None,
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for chunk_rank, row in enumerate(rows, 1):
        did = _doc_id(row)
        if not did or did in seen:
            continue
        seen.add(did)
        item = dict(row)
        item["best_chunk_rank"] = chunk_rank
        result.append(item)
        if max_docs and len(result) >= max_docs:
            break
    return result


class RetrieverAgent:
    def __init__(
        self,
        embedding_service: Any,
        milvus_client: Any,
        search_backend: Optional[Any] = None,
    ) -> None:
        self._embedding = embedding_service
        self._milvus = milvus_client
        self._backend = search_backend or DocumentSearchBackend(milvus_client)
        self._title_resolver = DocumentTitleResolver(self._backend)
        self._document_ranker = DocumentCandidateRanker()

        self._embedding_cache: Dict[str, Tuple[float, List[float]]] = {}
        self._channel_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

        logger.info(
            "[OK] RetrieverAgent initialized | "
            "mode=document-first multi-channel"
        )

    # ------------------------------------------------------------------
    # Public API — signature intentionally preserved.
    # ------------------------------------------------------------------
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
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        del history, statute_from_registry, kwargs  # preserved for API compatibility

        try:
            return await self._run_multichannel(
                query=query,
                enriched_query=enriched_query or query,
                top_k=max(1, int(top_k)),
                min_score=float(min_score or 0.0),
                statute_filter=statute_filter,
                domain=domain,
                jurisdiction=jurisdiction,
                subdomain_candidates=subdomain_candidates,
                b2b_b2c=b2b_b2c,
                statute_explicit=bool(statute_explicit),
            )
        except Exception as exc:
            # Safety valve: architecture failure must not take down the legal chat.
            logger.error(
                "Multi-channel retrieval failed; using compatibility rescue search: %s",
                exc,
                exc_info=True,
            )
            return await self._compatibility_rescue(
                query=query,
                enriched_query=enriched_query or query,
                top_k=max(1, int(top_k)),
                statute_filter=statute_filter,
                domain=domain,
                jurisdiction=jurisdiction,
                subdomain_candidates=subdomain_candidates,
                b2b_b2c=b2b_b2c,
            )

    # ------------------------------------------------------------------
    # Main architecture
    # ------------------------------------------------------------------
    async def _run_multichannel(
        self,
        *,
        query: str,
        enriched_query: str,
        top_k: int,
        min_score: float,
        statute_filter: Optional[str],
        domain: Optional[str],
        jurisdiction: Optional[str],
        subdomain_candidates: Optional[List[str]],
        b2b_b2c: Optional[str],
        statute_explicit: bool,
    ) -> List[Dict[str, Any]]:
        embedding = await self._embed(enriched_query)

        title_channels = self._title_resolver.discover(
            query,
            limit=TITLE_DOCUMENT_LIMIT,
        )

        channel_docs: Dict[str, List[Dict[str, Any]]] = {
            "title_exact_fuzzy": title_channels["title_exact_fuzzy"],
            "title_bm25": title_channels["title_bm25"],
        }
        channel_chunks: Dict[str, List[Dict[str, Any]]] = {}

        # 1) Precise statute channel — support signal, never the whole universe.
        if statute_filter:
            statute_k = max(STATUTE_MIN_CHUNK_K, top_k * 12)
            statute_chunks = self._cached_ann(
                cache_key=self._channel_key(
                    "statute",
                    enriched_query,
                    statute_filter,
                    None,
                    None,
                    None,
                    None,
                    statute_k,
                ),
                embedding=embedding,
                limit=statute_k,
                statute_filter=statute_filter,
            )
            channel_chunks["statute_ann"] = statute_chunks
            channel_docs["statute_ann"] = _unique_docs_from_chunks(
                statute_chunks,
                max_docs=TITLE_DOCUMENT_LIMIT,
            )
        else:
            channel_docs["statute_ann"] = []

        # 2) Routed subdomain channel — highest precision, but not mandatory.
        if subdomain_candidates:
            sub_k = min(
                SUBDOMAIN_MAX_CHUNK_K,
                max(SUBDOMAIN_MIN_CHUNK_K, top_k * 12),
            )
            sub_chunks = self._cached_ann(
                cache_key=self._channel_key(
                    "subdomain",
                    enriched_query,
                    None,
                    domain,
                    subdomain_candidates,
                    jurisdiction,
                    b2b_b2c,
                    sub_k,
                ),
                embedding=embedding,
                limit=sub_k,
                domain=domain,
                subdomains=subdomain_candidates,
                jurisdiction=jurisdiction,
                b2b_b2c=b2b_b2c,
            )
            channel_chunks["subdomain_ann"] = sub_chunks
            channel_docs["subdomain_ann"] = _unique_docs_from_chunks(
                sub_chunks,
                max_docs=TITLE_DOCUMENT_LIMIT,
            )
        else:
            channel_docs["subdomain_ann"] = []

        # 3) Domain-wide channel — survives wrong subdomain classification.
        if domain:
            domain_k = min(
                DOMAIN_MAX_CHUNK_K,
                max(DOMAIN_MIN_CHUNK_K, top_k * 20),
            )
            domain_chunks = self._cached_ann(
                cache_key=self._channel_key(
                    "domain",
                    enriched_query,
                    None,
                    domain,
                    None,
                    None,
                    None,
                    domain_k,
                ),
                embedding=embedding,
                limit=domain_k,
                domain=domain,
            )
            channel_chunks["domain_ann"] = domain_chunks
            channel_docs["domain_ann"] = _unique_docs_from_chunks(
                domain_chunks,
                max_docs=TITLE_DOCUMENT_LIMIT,
            )
        else:
            channel_docs["domain_ann"] = []

        # 4) Broad corpus channel — survives wrong domain classification.
        broad_k = min(
            BROAD_MAX_CHUNK_K,
            max(BROAD_MIN_CHUNK_K, top_k * 25),
        )
        broad_chunks = self._cached_ann(
            cache_key=self._channel_key(
                "broad",
                enriched_query,
                None,
                None,
                None,
                None,
                None,
                broad_k,
            ),
            embedding=embedding,
            limit=broad_k,
        )
        channel_chunks["broad_ann"] = broad_chunks
        channel_docs["broad_ann"] = _unique_docs_from_chunks(
            broad_chunks,
            max_docs=TITLE_DOCUMENT_LIMIT,
        )

        # 5) Document-level fusion.
        doc_limit = max(
            MIN_DOCUMENT_CANDIDATES,
            min(MAX_DOCUMENT_CANDIDATES, top_k + 5),
        )
        ranked_documents = self._document_ranker.rank(
            channel_docs,
            limit=doc_limit,
            requested_domain=domain,
            requested_subdomains=subdomain_candidates,
            statute_explicit=statute_explicit,
        )

        if not ranked_documents:
            logger.warning(
                "RetrieverAgent: no document candidates for query=%r",
                query[:80],
            )
            return []

        top_doc_ids = [_doc_id(x) for x in ranked_documents if _doc_id(x)]
        doc_meta = {_doc_id(x): x for x in ranked_documents if _doc_id(x)}

        logger.info(
            "Document-first retrieval | query=%r | top_docs=%s",
            query[:70],
            [
                (
                    d.get("document_rank"),
                    _doc_id(d),
                    round(float(d.get("document_score", 0.0)), 5),
                )
                for d in ranked_documents[:8]
            ],
        )

        # 6) Build a chunk universe only from winning documents.
        selected_k = min(
            SELECTED_DOC_MAX_CHUNK_K,
            max(SELECTED_DOC_MIN_CHUNK_K, top_k * 16),
        )
        selected_chunks = self._cached_ann(
            cache_key=self._channel_key(
                "selected_docs",
                enriched_query,
                ",".join(top_doc_ids),
                None,
                None,
                None,
                None,
                selected_k,
            ),
            embedding=embedding,
            limit=selected_k,
            document_ids=top_doc_ids,
        )

        candidates = self._build_chunk_pool(
            ranked_documents=ranked_documents,
            selected_chunks=selected_chunks,
            seed_channel_chunks=channel_chunks,
        )
        if not candidates:
            return []

        # 7) Existing BM25/RRF remains the chunk-level reranker.
        # Ask it for a wider intermediate window so document prior can still act.
        intermediate_k = min(
            len(candidates),
            max(top_k * 4, 20),
        )
        reranked = BM25Reranker.rerank(
            results=candidates,
            raw_query=query,
            top_k=intermediate_k,
            rrf_k=RRF_K_CONSTANT,
        )

        # 8) Document-aware final chunk selection.
        #
        # The document discovery/ranking layer has already decided which legal
        # documents are strongest.  The old implementation could still return
        # zero chunks from document rank #1 because one global chunk BM25 pass
        # was allowed to consume every final slot.
        #
        # New rule:
        #   - reserve >=1 relevant chunk from document rank #1;
        #   - reserve up to 2 when rank #1 is an exact-title match and top_k>=3;
        #   - fill every remaining slot from the existing global BM25/RRF order.
        #
        # This changes ONLY document -> chunk selection.  All retrieval channels,
        # document fusion, routing, RAGService and generator contracts stay the same.
        final_ranked = self._select_final_chunks(
            query=query,
            reranked=reranked,
            candidates=candidates,
            ranked_documents=ranked_documents,
            doc_meta=doc_meta,
            top_k=top_k,
            min_score=min_score,
        )

        return [self._validate_chunk(x) for x in final_ranked]

    # ------------------------------------------------------------------
    # Chunk pool / metadata propagation
    # ------------------------------------------------------------------
    def _build_chunk_pool(
        self,
        *,
        ranked_documents: Sequence[Dict[str, Any]],
        selected_chunks: Sequence[Dict[str, Any]],
        seed_channel_chunks: Dict[str, Sequence[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        doc_meta = {_doc_id(x): x for x in ranked_documents if _doc_id(x)}
        selected_ids = set(doc_meta)

        pool: Dict[str, Dict[str, Any]] = {}

        def add(row: Dict[str, Any]) -> None:
            did = _doc_id(row)
            if did not in selected_ids:
                return
            item = dict(row)
            meta = doc_meta[did]
            item["document_rank"] = int(meta.get("document_rank") or 0)
            item["document_score"] = float(meta.get("document_score") or 0.0)
            item["retrieval_channels"] = list(meta.get("retrieval_channels") or [])
            item["canonical_document_id"] = did
            item["document_id"] = did
            item["source_doc_url"] = (
                item.get("source_doc_url")
                or item.get("source_url")
                or item.get("url")
                or ""
            )
            item["source_url"] = (
                item.get("source_url")
                or item.get("source_doc_url")
                or item.get("url")
                or ""
            )
            item["url"] = item.get("url") or item["source_url"]

            key = _chunk_key(item)
            existing = pool.get(key)
            if existing is None or float(item.get("score", 0.0)) > float(existing.get("score", 0.0)):
                pool[key] = item

        # Selected-document ANN supplies the main chunk universe.
        for row in selected_chunks:
            add(dict(row))

        # Preserve a few strong seed chunks from every ANN channel.
        # This prevents the second ANN search from erasing a document that was
        # already discovered by an independent channel.
        for channel_name, rows in seed_channel_chunks.items():
            counts: Dict[str, int] = defaultdict(int)
            for row in rows:
                did = _doc_id(row)
                if did not in selected_ids:
                    continue
                if counts[did] >= SEED_CHUNKS_PER_DOC_PER_CHANNEL:
                    continue
                seeded = dict(row)
                seeded["seed_channel"] = channel_name
                add(seeded)
                counts[did] += 1

        # Stable order: document rank first, then dense similarity.
        result = list(pool.values())
        result.sort(
            key=lambda x: (
                int(x.get("document_rank") or 999),
                -float(x.get("score", 0.0)),
            )
        )
        return result


    # ------------------------------------------------------------------
    # Final document -> chunk selection
    # ------------------------------------------------------------------
    def _decorate_final_chunk(
        self,
        item: Dict[str, Any],
        doc_meta: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Apply the existing bounded document prior and propagate document metadata.

        This preserves the scoring behavior that already existed before this patch.
        """
        row = dict(item)
        did = _doc_id(row)
        dmeta = doc_meta.get(did, {})
        doc_rank = int(
            dmeta.get("document_rank")
            or row.get("document_rank")
            or 999
        )
        exact = bool(dmeta.get("exact_title_match"))

        base_score = float(row.get("score", 0.0))
        doc_prior = 0.020 / max(1, doc_rank)
        if exact:
            doc_prior += 0.030

        row["score"] = base_score + doc_prior
        row["document_rank"] = doc_rank if doc_rank != 999 else 0
        row["document_score"] = float(dmeta.get("document_score", 0.0))
        row["retrieval_channels"] = list(
            dmeta.get("retrieval_channels") or []
        )
        row["retrieval_mode"] = "multichannel_document_first"
        return row

    def _rank_chunks_within_top_document(
        self,
        *,
        query: str,
        candidates: Sequence[Dict[str, Any]],
        top_document_id: str,
        required_count: int,
        doc_meta: Dict[str, Dict[str, Any]],
        min_score: float,
    ) -> List[Dict[str, Any]]:
        """
        Rank chunks *inside* document rank #1.

        A separate local rerank is important because the global chunk reranker can
        otherwise give every available slot to chunks from competing documents.
        """
        if not top_document_id or required_count <= 0:
            return []

        top_doc_candidates = [
            dict(row)
            for row in candidates
            if _doc_id(row) == top_document_id
            and str(row.get("text") or "").strip()
        ]
        if not top_doc_candidates:
            return []

        # candidates are already stable-sorted by document rank and dense score.
        # Use the existing BM25/RRF implementation again, but only inside the
        # winning document.  If rank_bm25 is unavailable, its existing fallback
        # preserves dense order.
        local_k = min(
            len(top_doc_candidates),
            max(
                TOP_DOCUMENT_LOCAL_RERANK_LIMIT,
                required_count * 3,
            ),
        )
        locally_ranked = BM25Reranker.rerank(
            results=top_doc_candidates,
            raw_query=query,
            top_k=local_k,
            rrf_k=RRF_K_CONSTANT,
        )

        output: List[Dict[str, Any]] = []
        for row in locally_ranked:
            decorated = self._decorate_final_chunk(row, doc_meta)
            if min_score and float(decorated.get("score", 0.0)) < min_score:
                continue
            output.append(decorated)

        output.sort(
            key=lambda x: float(x.get("score", 0.0)),
            reverse=True,
        )
        return output

    def _select_final_chunks(
        self,
        *,
        query: str,
        reranked: Sequence[Dict[str, Any]],
        candidates: Sequence[Dict[str, Any]],
        ranked_documents: Sequence[Dict[str, Any]],
        doc_meta: Dict[str, Dict[str, Any]],
        top_k: int,
        min_score: float,
    ) -> List[Dict[str, Any]]:
        """
        Select final chunks while respecting the already-computed document rank.

        Policy:
        - rank #1 document is guaranteed representation when it has eligible chunks;
        - when rank #1 is an exact-title match and it has >= top_k eligible chunks,
          all final slots come from that requested document;
        - when an exact-title document has fewer than top_k eligible chunks, use all
          of its eligible chunks and fill only the remaining slots globally;
        - non-exact/natural queries keep the existing mixed-document behavior;
        - no query-specific IDs, titles or legal concepts are hard-coded.
        """
        if top_k <= 0:
            return []

        global_ranked: List[Dict[str, Any]] = []
        for item in reranked:
            row = self._decorate_final_chunk(item, doc_meta)
            if min_score and float(row.get("score", 0.0)) < min_score:
                continue
            global_ranked.append(row)

        global_ranked.sort(
            key=lambda x: float(x.get("score", 0.0)),
            reverse=True,
        )

        if not ranked_documents:
            return global_ranked[:top_k]

        top_doc = ranked_documents[0]
        top_doc_id = _doc_id(top_doc)
        exact_title = bool(top_doc.get("exact_title_match"))

        # Rank the top document locally before deciding how many slots it owns.
        #
        # Exact-title match = high-confidence specific-document request.
        # If it has enough eligible chunks, it should supply the whole final
        # context rather than being contaminated by a forced diversity document.
        requested_local_count = (
            top_k
            if exact_title
            else TOP_DOCUMENT_MIN_RESERVED_CHUNKS
        )

        top_doc_ranked = self._rank_chunks_within_top_document(
            query=query,
            candidates=candidates,
            top_document_id=top_doc_id,
            required_count=requested_local_count,
            doc_meta=doc_meta,
            min_score=min_score,
        )

        if exact_title:
            reserved_count = min(top_k, len(top_doc_ranked))
        else:
            reserved_count = min(
                TOP_DOCUMENT_MIN_RESERVED_CHUNKS,
                len(top_doc_ranked),
                top_k,
            )

        selected: List[Dict[str, Any]] = []
        seen = set()

        def add(row: Dict[str, Any]) -> bool:
            key = _chunk_key(row)
            if not key or key in seen:
                return False
            seen.add(key)
            selected.append(dict(row))
            return True

        # First, make sure document rank #1 cannot disappear entirely.
        reserved_added = 0
        for row in top_doc_ranked:
            if reserved_added >= reserved_count:
                break
            if add(row):
                reserved_added += 1

        # Exact-title path:
        # if the requested document already supplied enough eligible chunks,
        # selection is complete. Do not force an unrelated "diversity" document.
        if exact_title and len(selected) >= top_k:
            final_selected = selected[:top_k]
        else:
            # Non-exact queries, or exact-title documents with too few eligible
            # chunks, keep the existing global BM25/RRF fill behavior.
            for row in global_ranked:
                if len(selected) >= top_k:
                    break
                add(row)

            # Rare safety fallback: if the global rerank window was smaller than
            # top_k, fill from the already-built candidate pool without another
            # Milvus search.
            if len(selected) < top_k:
                fallback_rows = [
                    self._decorate_final_chunk(row, doc_meta)
                    for row in candidates
                    if str(row.get("text") or "").strip()
                ]
                fallback_rows.sort(
                    key=lambda x: (
                        int(x.get("document_rank") or 999),
                        -float(x.get("score", 0.0)),
                    )
                )
                for row in fallback_rows:
                    if len(selected) >= top_k:
                        break
                    if min_score and float(row.get("score", 0.0)) < min_score:
                        continue
                    add(row)

            final_selected = selected[:top_k]

        doc_counts: Dict[str, int] = defaultdict(int)
        for row in final_selected:
            doc_counts[_doc_id(row)] += 1

        logger.info(
            "Final chunk selection | top_doc=%s | exact_title=%s | "
            "reserved_requested=%s | reserved_added=%s | "
            "exact_document_full_context=%s | doc_counts=%s",
            top_doc_id,
            exact_title,
            reserved_count,
            reserved_added,
            bool(exact_title and reserved_added >= top_k),
            dict(doc_counts),
        )

        return final_selected


    # ------------------------------------------------------------------
    # Caches
    # ------------------------------------------------------------------
    async def _embed(self, enriched_query: str) -> List[float]:
        key = str(enriched_query)
        now = time.monotonic()
        cached = self._embedding_cache.get(key)
        if cached and (now - cached[0]) < EMBED_CACHE_SECONDS:
            return list(cached[1])

        embedding = await self._embedding.embed_query(enriched_query)
        self._embedding_cache[key] = (now, list(embedding))

        # bounded opportunistic cleanup
        if len(self._embedding_cache) > 64:
            cutoff = now - EMBED_CACHE_SECONDS
            self._embedding_cache = {
                k: v for k, v in self._embedding_cache.items()
                if v[0] >= cutoff
            }
        return embedding

    def _channel_key(
        self,
        channel: str,
        query: str,
        statute: Optional[str],
        domain: Optional[str],
        subdomains: Optional[Sequence[str]],
        jurisdiction: Optional[str],
        b2b: Optional[str],
        limit: int,
    ) -> str:
        return "|".join(
            [
                channel,
                str(query),
                str(statute or ""),
                str(domain or ""),
                ",".join(sorted(str(x) for x in (subdomains or []))),
                str(jurisdiction or ""),
                str(b2b or ""),
                str(limit),
            ]
        )

    def _cached_ann(self, cache_key: str, embedding: List[float], **kwargs: Any) -> List[Dict[str, Any]]:
        now = time.monotonic()
        cached = self._channel_cache.get(cache_key)
        if cached and (now - cached[0]) < CHANNEL_CACHE_SECONDS:
            return [dict(x) for x in cached[1]]

        rows = self._backend.search_ann(embedding, **kwargs)
        self._channel_cache[cache_key] = (now, [dict(x) for x in rows])

        if len(self._channel_cache) > 128:
            cutoff = now - CHANNEL_CACHE_SECONDS
            self._channel_cache = {
                k: v for k, v in self._channel_cache.items()
                if v[0] >= cutoff
            }
        return rows

    # ------------------------------------------------------------------
    # Compatibility rescue
    # ------------------------------------------------------------------
    async def _compatibility_rescue(
        self,
        *,
        query: str,
        enriched_query: str,
        top_k: int,
        statute_filter: Optional[str],
        domain: Optional[str],
        jurisdiction: Optional[str],
        subdomain_candidates: Optional[List[str]],
        b2b_b2c: Optional[str],
    ) -> List[Dict[str, Any]]:
        embedding = await self._embedding.embed_query(enriched_query)
        fetch_k = max(top_k * 8, 50)

        # First try the existing client's domain search, then broad.
        attempts = [
            dict(
                statute_filter=statute_filter,
                domain=domain,
                jurisdiction=jurisdiction,
                subdomain_candidates=subdomain_candidates,
                b2b_b2c=b2b_b2c,
                fallback_level=0,
            ),
            dict(
                statute_filter=None,
                domain=domain,
                jurisdiction=None,
                subdomain_candidates=None,
                b2b_b2c=None,
                fallback_level=4,
            ),
            dict(
                statute_filter=None,
                domain=None,
                jurisdiction=None,
                subdomain_candidates=None,
                b2b_b2c=None,
                fallback_level=4,
            ),
        ]

        candidates: List[Dict[str, Any]] = []
        for params in attempts:
            try:
                rows = self._milvus.search(
                    embedding=embedding,
                    top_k=fetch_k,
                    **params,
                )
            except Exception:
                rows = []
            if rows:
                candidates.extend(rows)

        # Deduplicate before old chunk BM25.
        dedup: Dict[str, Dict[str, Any]] = {}
        for row in candidates:
            key = _chunk_key(row)
            if key not in dedup or float(row.get("score", 0.0)) > float(dedup[key].get("score", 0.0)):
                dedup[key] = dict(row)

        reranked = BM25Reranker.rerank(
            results=list(dedup.values()),
            raw_query=query,
            top_k=top_k,
            rrf_k=RRF_K_CONSTANT,
        )
        return [self._validate_chunk(x) for x in reranked]

    # Retained because earlier tests/tools call this method directly.
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
            logger.error(
                "Milvus compatibility search L%s failed: %s",
                fallback_level,
                exc,
            )
            return []

    def _validate_chunk(self, item: Dict[str, Any]) -> Dict[str, Any]:
        source_url = str(
            item.get("source_url")
            or item.get("source_doc_url")
            or item.get("url")
            or ""
        )
        did = _doc_id(item)

        chunk_obj = RetrievedChunk(
            text=str(item.get("text", "")),
            score=float(item.get("score", 0.0)),
            score_dense=float(item.get("score_dense", item.get("score", 0.0))),
            score_bm25=float(item.get("score_bm25", 0.0)),
            source_doc_url=source_url,
            section_ref=str(
                item.get("section_ref")
                or item.get("section_number")
                or item.get("citation_anchor")
                or ""
            ),
            url=source_url,
            domain=str(item.get("domain") or item.get("domain_name") or item.get("domain_id") or ""),
            subdomain=str(item.get("subdomain") or item.get("subdomain_name") or item.get("subdomain_id") or ""),
            chunk_id=str(item.get("chunk_id", "")),
            document_id=did,
            fallback_level=int(item.get("fallback_level", 0) or 0),
            source_url=source_url,
            doc_title=str(item.get("doc_title") or item.get("law_title") or ""),
            canonical_document_id=did,
            document_rank=int(item.get("document_rank", 0) or 0),
            document_score=float(item.get("document_score", 0.0) or 0.0),
            retrieval_mode=str(item.get("retrieval_mode") or "multichannel_document_first"),
            retrieval_channels=list(item.get("retrieval_channels") or []),
        )
        return chunk_obj.model_dump()
