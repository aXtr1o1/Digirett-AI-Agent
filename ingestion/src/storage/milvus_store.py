from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional
from pymilvus import (
    Collection,
    connections,
    utility,
)
from ingestion.src.config import (
    MILVUS_HOST,
    MILVUS_PORT,
    MILVUS_COLLECTION,
    MILVUS_BATCH_SIZE,
    MILVUS_MAX_RETRIES,
    MILVUS_METRIC_TYPE,
    MILVUS_INDEX_TYPE,
)
from ingestion.schema.milvus_schema import (
    DEFAULT_VECTOR_DIM,
    get_collection_schema,
)

logger = logging.getLogger(__name__)


class MilvusChunkStore:
    """Milvus Vector Store for digirett_legal_chunks_v1 collection."""

    def __init__(
        self,
        collection_name: Optional[str] = None,
        vector_dim: int = DEFAULT_VECTOR_DIM,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        self.collection_name = collection_name or MILVUS_COLLECTION
        self.vector_dim = vector_dim
        self.embedding_dim = vector_dim
        self.host = host or MILVUS_HOST
        self.port = port or MILVUS_PORT
        self._connected = False
        self.collection: Optional[Collection] = None

    def _fix_embedding(self, emb: Any) -> List[float]:
        """Validates and flattens/converts embedding to List[float]."""
        if not isinstance(emb, (list, tuple)):
            raise TypeError(f"Expected list/tuple embedding, got {type(emb).__name__}")
        if not emb:
            raise ValueError("Embedding list is empty")
        if isinstance(emb[0], (list, tuple)):
            emb = emb[0]
        expected_dim = getattr(self, "embedding_dim", getattr(self, "vector_dim", DEFAULT_VECTOR_DIM))
        if len(emb) != expected_dim:
            raise ValueError(f"Embedding dim mismatch: expected {expected_dim}, got {len(emb)}")
        return [float(x) for x in emb]

    def _ensure_connection(self) -> bool:
        if not self._connected:
            try:
                connections.connect(alias="default", host=self.host, port=self.port, timeout=30)
                if not utility.has_collection(self.collection_name):
                    schema = get_collection_schema(vector_dim=self.vector_dim)
                    self.collection = Collection(name=self.collection_name, schema=schema)
                    index_params = {
                        "metric_type": MILVUS_METRIC_TYPE,
                        "index_type": MILVUS_INDEX_TYPE,
                        "params": {"M": 16, "efConstruction": 200},
                    }
                    self.collection.create_index(field_name="embedding", index_params=index_params)
                else:
                    self.collection = Collection(self.collection_name)

                self.collection.load()
                self._connected = True
                logger.info("MilvusChunkStore: Connected to %s:%s | Collection: %s", self.host, self.port, self.collection_name)
            except Exception as exc:
                logger.warning("MilvusChunkStore: Connection warning (%s:%s): %s", self.host, self.port, exc)
                return False
        return True

    def _extract_field_value(self, item: Dict[str, Any], field_name: str) -> Any:
        """Extracts and formats a value for a specific Milvus canonical schema field."""
        if field_name == "chunk_id":
            return str(item.get("chunk_id", ""))[:128]
        if field_name == "legal_document_id":
            return str(item.get("legal_document_id") or item.get("canonical_document_id", ""))[:128]
        if field_name == "legal_section_id":
            return str(item.get("legal_section_id", ""))[:128]
        if field_name == "canonical_document_id":
            return str(item.get("canonical_document_id", ""))[:255]
        if field_name == "source_section_key":
            return str(item.get("source_section_key", ""))[:255]
        if field_name == "chunk_index":
            return int(item.get("chunk_index", 0))
        if field_name == "embedding":
            return self._fix_embedding(item["embedding"])
        if field_name == "text":
            return str(item.get("text", ""))[:65535]
        if field_name == "document_type":
            return str(item.get("document_type", "lov"))[:30]
        if field_name == "doc_title":
            return str(item.get("doc_title", "Untitled"))[:512]
        if field_name == "section_number":
            return str(item.get("section_number", ""))[:100]
        if field_name == "section_title":
            return str(item.get("section_title", ""))[:512]
        if field_name == "citation_anchor":
            return str(item.get("citation_anchor", ""))[:255]
        if field_name == "source_url":
            return str(item.get("source_url", ""))[:512]
        if field_name == "domain_id":
            return str(item.get("domain_id", ""))[:64]
        if field_name == "domain_name":
            return str(item.get("domain_name", ""))[:255]
        if field_name == "subdomain_id":
            return str(item.get("subdomain_id", ""))[:64]
        if field_name == "subdomain_name":
            return str(item.get("subdomain_name", ""))[:255]
        if field_name == "taxonomy_version":
            return str(item.get("taxonomy_version", "1.1.0"))[:20]
        if field_name == "parent_law_canonical_id":
            return str(item.get("parent_law_canonical_id", ""))[:255]
        if field_name == "parent_law_title":
            return str(item.get("parent_law_title", ""))[:512]
        if field_name == "jurisdiction":
            val = item.get("jurisdiction") or item.get("jurisdictions", "NO")
            return (",".join(val) if isinstance(val, (list, tuple)) else str(val))[:100]
        if field_name == "b2b_b2c":
            val = item.get("b2b_b2c") or item.get("b2b_b2c_types", "BOTH")
            return (",".join(val) if isinstance(val, (list, tuple)) else str(val))[:20]
        if field_name == "relationship_type":
            val = item.get("relationship_type") or item.get("relationship_types", "commercial")
            return (",".join(val) if isinstance(val, (list, tuple)) else str(val))[:50]
        if field_name == "source_type":
            val = item.get("source_type", "lov")
            return (",".join(val) if isinstance(val, (list, tuple)) else str(val))[:50]
        if field_name == "tier":
            val = item.get("tier", "1")
            return (",".join(val) if isinstance(val, (list, tuple)) else str(val))[:30]
        if field_name == "language":
            return str(item.get("language", "no"))[:10]
        if field_name == "version_date":
            return str(item.get("version_date", ""))[:30]
        if field_name == "content_hash":
            return str(item.get("content_hash", ""))[:64]
        if field_name == "is_current":
            return bool(item.get("is_current", True))
        if field_name == "retrieval_enabled":
            return bool(item.get("retrieval_enabled", True))
        return str(item.get(field_name, ""))

    def _wait_for_network_recovery(self, check_interval: float = 10.0, max_wait_seconds: float = 120.0) -> None:
        """Pauses execution and probes network connectivity with a timeout until connection is restored."""
        logger.warning("[NETWORK OFFLINE] Milvus connection lost. Pausing vector storage. Waiting for reconnection...")
        import socket
        start_time = time.time()
        while time.time() - start_time < max_wait_seconds:
            time.sleep(check_interval)
            is_online = False
            for host, port in [("8.8.8.8", 53), ("1.1.1.1", 53)]:
                try:
                    with socket.create_connection((host, port), timeout=4.0):
                        is_online = True
                        break
                except OSError:
                    pass

            if is_online:
                logger.info("[NETWORK RESTORED] Internet connection re-established. Reconnecting to Milvus...")
                self._connected = False
                self._ensure_connection()
                return
            logger.warning("[WAITING FOR CONNECTION] Still disconnected. Retrying in %ds...", int(check_interval))
        raise ConnectionError(f"Milvus network recovery timed out after {int(max_wait_seconds)} seconds.")

    def _insert_single_batch(self, items: List[Dict[str, Any]]) -> int:
        """Inserts a single columnar batch into Milvus strictly matching collection schema."""
        if not items or not self.collection:
            return 0

        columnar_data = []
        for field in self.collection.schema.fields:
            max_len = getattr(field, "max_length", None)
            if not max_len and hasattr(field, "params") and field.params:
                max_len = field.params.get("max_length")

            col = []
            for item in items:
                val = self._extract_field_value(item, field.name)
                if max_len and isinstance(val, str) and len(val) > max_len:
                    val = val[:max_len]
                col.append(val)
            columnar_data.append(col)

        self.collection.insert(columnar_data, timeout=15.0)
        self.collection.flush(timeout=15.0)
        return len(items)

    def insert_chunks(
        self,
        items: List[Dict[str, Any]],
        batch_size: int = MILVUS_BATCH_SIZE,
        max_retries: int = MILVUS_MAX_RETRIES,
    ) -> int:
        """Inserts records into Milvus in safe micro-batches with automatic retries."""
        if not items:
            return 0

        if not self._ensure_connection() or not self.collection:
            logger.warning("Milvus connection not available — skipping chunk insertion.")
            return 0

        total_inserted = 0
        total_items = len(items)
        total_batches = (total_items + batch_size - 1) // batch_size

        for b_idx in range(total_batches):
            batch_items = items[b_idx * batch_size : (b_idx + 1) * batch_size]
            success = False
            for attempt in range(1, max_retries + 1):
                try:
                    self._insert_single_batch(batch_items)
                    total_inserted += len(batch_items)
                    success = True
                    break
                except Exception as exc:
                    logger.warning(
                        "Milvus micro-batch %d/%d insertion attempt %d failed: %s",
                        b_idx + 1, total_batches, attempt, exc
                    )
                    time.sleep(1.0 * attempt)
                    self._connected = False
                    if attempt >= max_retries:
                        self._wait_for_network_recovery()
                    else:
                        self._ensure_connection()

            if not success:
                logger.error("Milvus micro-batch %d/%d failed after retries.", b_idx + 1, total_batches)

        logger.info("MilvusChunkStore: Successfully inserted %d/%d chunks into collection '%s'", total_inserted, total_items, self.collection_name)
        return total_inserted

    def delete_chunks_by_document_id(self, canonical_document_id: str) -> bool:
        """Deletes all vector chunks associated with a canonical document ID."""
        if not canonical_document_id:
            return False
        if not self._ensure_connection() or not self.collection:
            logger.warning("Milvus connection not available — skipping chunk deletion.")
            return False
        try:
            field_names = [f.name for f in self.collection.schema.fields]
            if "canonical_source_id" in field_names:
                expr = f'canonical_source_id == "{canonical_document_id}"'
            elif "document_id" in field_names:
                expr = f'document_id == "{canonical_document_id}"'
            elif "canonical_document_id" in field_names:
                expr = f'canonical_document_id == "{canonical_document_id}"'
            else:
                expr = f'chunk_id like "{canonical_document_id}%"'

            self.collection.delete(expr)
            self.collection.flush()
            logger.info("Milvus: Purged existing vector chunks for document '%s'", canonical_document_id)
            return True
        except Exception as exc:
            logger.warning("Milvus: Failed to delete chunks for document '%s': %s", canonical_document_id, exc)
            return False

    def delete_chunks_by_document_ids(self, doc_ids: List[str]) -> int:
        """Deletes vector chunks for multiple canonical document IDs."""
        if not doc_ids:
            return 0
        deleted_count = 0
        for doc_id in doc_ids:
            if self.delete_chunks_by_document_id(doc_id):
                deleted_count += 1
        return deleted_count

    def purge_unmapped_subdomain_chunks(self) -> bool:
        """Deletes all vector chunks with subdomain_id == 'NO_SUBDOMAIN' or empty from the collection."""
        if not self._ensure_connection() or not self.collection:
            return False
        try:
            expr = 'subdomain_id == "NO_SUBDOMAIN" or subdomain_id == ""'
            self.collection.delete(expr)
            self.collection.flush()
            logger.info("Milvus: Purged unmapped NO_SUBDOMAIN chunks from collection '%s'", self.collection_name)
            return True
        except Exception as exc:
            logger.warning("Milvus: Failed to purge NO_SUBDOMAIN chunks: %s", exc)
            return False