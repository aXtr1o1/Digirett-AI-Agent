"""
Milvus vector database client — singleton.

Handles connection, collection loading, and HNSW approximate nearest-neighbor search.
All vector search calls go through this class.
"""

import logging
from typing import Any, Dict, List, Optional

from pymilvus import connections, Collection, utility
from tenacity import retry, stop_after_attempt, wait_exponential
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)



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
        top_k: int = 5,
        min_score: float = 0.8,
        output_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
       
        if not self._ready or self._collection is None:
            raise RuntimeError(
                "Milvus collection not initialized. Call connect() first."
            )

        if output_fields is None:
            output_fields = [
                "chunk_id",
                "file_name",
                "text",
                "parent_title",
                "parent_type",
                "chunk_index",
                "parent_index",
                "child_index",
                "url",
            ]

        try:
            logger.info(
                f" Milvus search | collection={self.collection_name} | "
                f"top_k={top_k} | min_score={min_score}"
            )

            results = self._collection.search(
                data=[embedding],
                anns_field="embedding",
                param={"metric_type": "IP", "params": {"ef": 64}},
                limit=top_k,
                output_fields=output_fields,
            )

            hits = []
            for batch in results:
                for hit in batch:
                    score = float(hit.distance)
                    if score < min_score:
                        continue

                    row: Dict[str, Any] = {"score": score}
                    for field in output_fields:
                        value = getattr(hit.entity, field, None)
                        if value is None and hasattr(hit.entity, "get"):
                            value = hit.entity.get(field)
                        row[field] = value

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