"""
Milvus vector database client — singleton.

Handles connection, collection loading, and HNSW approximate nearest-neighbor search.
All vector search calls go through this class.
"""

import logging
from typing import Any, Dict, List, Optional

from pymilvus import connections, Collection, utility
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)
loaded = utility.load_state(self.collection_name)

class MilvusClient:
    """
    Thread-safe singleton Milvus client.

    Call connect() once at startup (done in main.py lifespan).
    After that, all agents share the same collection reference.
    """

    _instance: Optional["MilvusClient"] = None

    def __new__(cls) -> "MilvusClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_ready"):
            self.host: Optional[str] = None
            self.port: Optional[int] = None
            self.collection_name: Optional[str] = None
            self._collection: Optional[Collection] = None
            self._ready = False

    # ── Connection ───────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=2))
    def connect(self, host: str, port: int, collection_name: str) -> None:
        """
        Connect to the Milvus server and load the target collection into memory.

        Args:
            host:            Milvus server hostname or IP.
            port:            Milvus server port (default 19530).
            collection_name: Name of the collection to search.

        Raises:
            ConnectionError: When the server is unreachable.
            ValueError:      When the collection does not exist.
        """
        try:
            logger.info(f"🔌 Connecting to Milvus at {host}:{port}...")

            self.host = host
            self.port = port
            self.collection_name = collection_name

            connections.connect(alias="default", host=host, port=port)

            if not utility.has_collection(collection_name):
                raise ValueError(
                    f"Collection '{collection_name}' does not exist in Milvus."
                )

            self._collection = Collection(collection_name)
            self._collection.load()

            self._ready = True
            logger.info(
                f"✅ Milvus connected | collection='{collection_name}' | "
                f"entities={self._collection.num_entities:,}"
            )

        except Exception as exc:
            logger.error(f"❌ Milvus connection failed | {exc}", exc_info=True)
            raise ConnectionError(f"Milvus connection failed: {exc}") from exc

    def check_connection(self) -> bool:
        """Ping Milvus by fetching entity count. Returns True when healthy."""
        try:
            if not self._ready or self._collection is None:
                return False
            _ = self._collection.num_entities
            return True
        except Exception as exc:
            logger.error(f"❌ Milvus health check failed | {exc}")
            return False

    def close(self) -> None:
        """Release the collection and disconnect."""
        try:
            if self._collection:
                self._collection.release()
                logger.info(f"📤 Released Milvus collection '{self.collection_name}'")
            connections.disconnect("default")
            self._ready = False
            self._collection = None
            logger.info("🔌 Milvus disconnected")
        except Exception as exc:
            logger.error(f"Error closing Milvus: {exc}")

    # ── Search ───────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=2))
    def search(
        self,
        embedding: List[float],
        metric_type: str,
        top_k: int = 50,
        min_score: float = 0.0,       # kept in signature — NOT used for filtering
        output_fields: Optional[List[str]] = None,
        statute_filter: Optional[str] = None,    # full Lovdata URL matched against statute_id
        domain: Optional[str] = None,            # matched against domain_name
        jurisdiction: Optional[str] = None,      # matched against jurisdiction field
        source_type: Optional[str] = None,       # matched against source_type field
    ) -> List[Dict[str, Any]]:
        """
        Search Milvus for nearest neighbours.

        NOTE: min_score is intentionally NOT applied here.
        Score filtering / thresholding is handled downstream by RerankerAgent
        so that the reranker receives the full recall set.
        """
        if not self._ready or self._collection is None:
            raise RuntimeError(
                "Milvus collection not initialized. Call connect() first."
            )
        if loaded != "Loaded":
            logger.warning("Milvus collection not loaded — loading now...")
            self._collection.load()

        if output_fields is None:
            output_fields = [
                "chunk_id",
                "domain_name",
                "sub_domain_name",
                "tags",
                "jurisdiction",
                "statute_id",
                "tier",
                "source_type",
                "chunk_index",
                "parent_index",
                "child_index",
                # ── Text payload — required for LLM generation ─────────────
                "text",
                "parent_title",
                "law_short_name",
                "paragraph_number",
            ]

        try:
            # ── Build Milvus filter expression ────────────────────────────
            # statute_filter is a full Lovdata URL → uniquely identifies one law.
            # When statute_id is set, do NOT also filter on domain_name:
            #   - statute_id is specific enough (one law = one URL)
            #   - the reasoning agent's domain may differ from the XL file stem
            #     (e.g. agent says "Avtalerett" but law is in "Arbeidsrett.xlsx")
            # domain_name filter is only applied when statute_id is NOT set.
            expr_parts = []

            if statute_filter:
                safe_filter = statute_filter.replace('"', '\\"')
                expr_parts.append(f'statute_id == "{safe_filter}"')
                # ↑ statute_id alone is sufficient — skip domain filter
            elif domain:
                # No statute_id → use domain to narrow the search space
                safe_domain = domain.replace('"', '\\"')
                expr_parts.append(f'domain_name == "{safe_domain}"')

            if jurisdiction and jurisdiction.lower() not in ("both", ""):
                safe_jur = jurisdiction.replace('"', '\\"')
                expr_parts.append(f'jurisdiction == "{safe_jur}"')

            # source_type intentionally NOT filtered — not stored consistently

            expr = " && ".join(expr_parts) if expr_parts else None

            logger.info(
                f"🔍 Milvus expr: {expr!r} | top_k={top_k}"
            )

            results = self._collection.search(
                data=[embedding],
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {"ef": 256}},
                limit=top_k,
                output_fields=output_fields,
                expr=expr,
            )

            hits = []
            for batch in results:
                for hit in batch:
                    score = float(hit.distance)

                    row: Dict[str, Any] = {"score": score}
                    for field in output_fields:
                        value = getattr(hit.entity, field, None)
                        if value is None and hasattr(hit.entity, "get"):
                            value = hit.entity.get(field)
                        row[field] = value

                    # Convenience aliases so downstream agents need no changes
                    row["url"] = row.get("statute_id")        # statute_id holds the Lovdata URL
                    row["file_name"] = row.get("statute_id")  # backward-compat alias

                    hits.append(row)

            logger.info(f"Milvus returned {len(hits)}/{top_k} results")
            return hits

        except Exception as exc:
            logger.error(f"❌ Milvus search failed | {exc}", exc_info=True)
            raise ValueError(f"Milvus search failed: {exc}") from exc

    def get_stats(self) -> Dict[str, Any]:
        """Return basic collection statistics for the health endpoint."""
        if not self._ready or self._collection is None:
            return {"status": "not_initialized"}
        try:
            return {
                "status": "connected",
                "collection_name": self.collection_name,
                "num_entities": self._collection.num_entities,
                "host": self.host,
                "port": self.port,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}


# Module-level singleton and DI factory
milvus_client = MilvusClient()


def get_milvus() -> MilvusClient:
    """Return the singleton MilvusClient (for dependency injection in main.py)."""
    return milvus_client
