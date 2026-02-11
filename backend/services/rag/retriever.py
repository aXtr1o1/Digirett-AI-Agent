import logging
from typing import Any, Dict, List, Tuple

from pymilvus import Collection

from backend.config import settings

logger = logging.getLogger(__name__)


class MilvusRetriever:
    def __init__(self, collection: Collection, metric_type: str = "COSINE"):
        self.collection = collection
        self.metric_type = (metric_type or "COSINE").upper()

    def _to_similarity(self, hit: Any) -> float:
        """
        Use hit.score as the primary signal.
        In pymilvus, `hit.score` is what Milvus returns for the configured metric.
        Avoid guessing/inverting unless score is missing.
        """
        score = getattr(hit, "score", None)
        if score is not None:
            try:
                return float(score)
            except Exception:
                return 0.0

        dist = getattr(hit, "distance", None)
        if dist is None:
            return 0.0
        try:
            d = float(dist)
            return 1.0 / (1.0 + d)
        except Exception:
            return 0.0

    def _diversify(self, rows: List[Dict[str, Any]], top_k: int, max_per_doc: int = 2) -> List[Dict[str, Any]]:
        picked: List[Dict[str, Any]] = []
        seen_chunk_ids: set[str] = set()
        per_doc: dict[str, int] = {}
        seen_parent: set[Tuple[str, int]] = set()

        for r in rows:
            cid = (r.get("chunk_id") or "").strip()
            if not cid or cid in seen_chunk_ids:
                continue

            file_name = (r.get("file_name") or "").strip()
            doc_key = file_name or (r.get("file_hash") or "unknown-doc")

            per_doc.setdefault(doc_key, 0)
            if per_doc[doc_key] >= max_per_doc:
                continue

            parent_idx = int(r.get("parent_index") or -1)
            parent_key = (doc_key, parent_idx)
            if parent_key in seen_parent:
                continue

            seen_chunk_ids.add(cid)
            per_doc[doc_key] += 1
            seen_parent.add(parent_key)
            picked.append(r)

            if len(picked) >= top_k:
                return picked

        for r in rows:
            if len(picked) >= top_k:
                break

            cid = (r.get("chunk_id") or "").strip()
            if not cid or cid in seen_chunk_ids:
                continue

            file_name = (r.get("file_name") or "").strip()
            doc_key = file_name or (r.get("file_hash") or "unknown-doc")

            per_doc.setdefault(doc_key, 0)
            if per_doc[doc_key] >= max_per_doc:
                continue

            seen_chunk_ids.add(cid)
            per_doc[doc_key] += 1
            picked.append(r)

        return picked

    def search(self, embedding: List[float], top_k: int, correlation_id: str) -> List[Dict[str, Any]]:
        logger.info(f"[{correlation_id}] Milvus search top_k={top_k} dim={len(embedding)} metric={self.metric_type}")

        fetch_k = min(max(top_k * 8, top_k), 120)

        # NOTE: This must match your Milvus index type. If you're on IVF, switch to nprobe.
        params = {"metric_type": self.metric_type, "params": {"ef": 128}}

        output_fields = [
            "chunk_id",
            "file_name",
            "file_hash",
            "chunk_index",
            "parent_index",
            "child_index",
            "parent_title",
            "parent_type",
            "text",
            "url",
            "doc_type",
            "omrade",
            "token_count",
        ]

        res = self.collection.search(
            data=[embedding],
            anns_field="embedding",
            param=params,
            limit=fetch_k,
            output_fields=output_fields,
        )

        rows: List[Dict[str, Any]] = []
        for hits in res:
            for hit in hits:
                sim = self._to_similarity(hit)
                if sim < float(settings.MIN_SIMILARITY_SCORE):  # keep at 0.40 in env
                    continue

                ent = hit.entity
                get = ent.get  # type: ignore[attr-defined]

                rows.append(
                    {
                        "score": float(sim),
                        "chunk_id": get("chunk_id"),
                        "file_name": get("file_name"),
                        "file_hash": get("file_hash"),
                        "chunk_index": get("chunk_index"),
                        "parent_index": get("parent_index"),
                        "child_index": get("child_index"),
                        "parent_title": get("parent_title"),
                        "parent_type": get("parent_type"),
                        "text": get("text"),
                        "url": (get("url") or "").strip(),
                        "doc_type": (get("doc_type") or "").strip(),
                        "omrade": (get("omrade") or "").strip(),
                        "token_count": get("token_count"),
                    }
                )

        rows.sort(key=lambda x: x["score"], reverse=True)
        final = self._diversify(rows, top_k=top_k, max_per_doc=2)

        if final:
            logger.info(f"[{correlation_id}] Milvus top scores: {[round(r['score'], 4) for r in final]}")
        else:
            logger.info(f"[{correlation_id}] Milvus returned 0 rows after MIN_SIMILARITY_SCORE filter")

        return final
