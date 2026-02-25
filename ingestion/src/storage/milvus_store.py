"""
MilvusTextStore — CPU-aware version
=====================================
All tuning constants are imported from config.py (which reads .env).
No os.getenv calls or numeric literals appear in this file.
"""

import logging
import sys
import time
import psutil

from ingestion.src.storage.supabase_store import SupabaseStore
from ingestion.src.config import (
    MILVUS_HOST,
    MILVUS_PORT,
    MILVUS_COLLECTION,
    MILVUS_DIMENSION,
    MILVUS_CONNECT_TIMEOUT,
    MILVUS_INSERT_BATCH,
    MILVUS_INSERT_SLEEP,
    MILVUS_FLUSH_EVERY,
    MILVUS_CPU_PAUSE_THRESHOLD,
    MILVUS_CPU_MAX_WAIT,
)

from typing import List, Dict, Any

from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)

logger = logging.getLogger(__name__)


def _wait_for_cpu(threshold: int, max_wait: int, label: str = "") -> None:
    """Block until CPU% drops below threshold or max_wait seconds elapsed."""
    waited = 0
    while waited < max_wait:
        cpu = psutil.cpu_percent(interval=1)
        if cpu < threshold:
            return
        logger.warning(
            f"⏳ Milvus: CPU {cpu}% > {threshold}% [{label}] — waiting 3s"
        )
        time.sleep(3)
        waited += 3
    logger.warning(f"⚠️  CPU still elevated after {max_wait}s — proceeding")


class MilvusTextStore:
    def __init__(self):
        self.collection_name = MILVUS_COLLECTION
        self.embedding_dim   = MILVUS_DIMENSION
        self._connected      = False
        self.collection      = None
        self.insert_counter  = 0

    def _ensure_connection(self):
        if not self._connected:
            connections.connect(
                alias="default",
                host=MILVUS_HOST,
                port=MILVUS_PORT,
                timeout=MILVUS_CONNECT_TIMEOUT,
            )
            self.collection = self._get_or_create_collection()
            self._connected = True

    def delete_by_file_name(self, file_name: str):
        self._ensure_connection()
        self.collection.delete(f'file_name == "{file_name}"')
        self.collection.flush()

    # ------------------------------------------------------------------
    # Embedding normalisation
    # ------------------------------------------------------------------
    def _fix_embedding(self, emb):
        if isinstance(emb, dict):
            emb = (
                emb.get("dense_vecs")
                or emb.get("embedding")
                or emb.get("vector")
            )
            if emb is None:
                raise ValueError("Could not extract embedding from dict")

        if hasattr(emb, "tolist"):
            emb = emb.tolist()

        while isinstance(emb, list) and len(emb) > 0 and isinstance(emb[0], list):
            emb = emb[0]

        if not isinstance(emb, list):
            raise TypeError(f"Embedding must be a list, got {type(emb)}")
        if not emb:
            raise ValueError("Embedding is empty")

        result = [float(x) for x in emb]

        if len(result) != self.embedding_dim:
            raise ValueError(
                f"Embedding dimension mismatch: "
                f"expected {self.embedding_dim}, got {len(result)}"
            )
        return result

    # ------------------------------------------------------------------
    # System state logging
    # ------------------------------------------------------------------
    def _log_system_state(self, stage: str, rows: int, payload_mb: float):
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        logger.info(
            f"[Milvus {stage}] rows={rows} | payload={payload_mb:.2f}MB "
            f"| cpu={cpu}% | mem={mem}%"
        )

    # ------------------------------------------------------------------
    # Collection (create or load)
    # ------------------------------------------------------------------
    def _get_or_create_collection(self) -> Collection:
        if utility.has_collection(self.collection_name):
            logger.info(f"✅ Loading existing collection: {self.collection_name}")
            col = Collection(self.collection_name)
            col.load()
            return col

        logger.info(f"🔨 Creating collection: {self.collection_name}")
        fields = [
            FieldSchema(name="id",           dtype=DataType.INT64,        is_primary=True, auto_id=True),
            FieldSchema(name="chunk_id",     dtype=DataType.VARCHAR,      max_length=128),
            FieldSchema(name="file_name",    dtype=DataType.VARCHAR,      max_length=255),
            FieldSchema(name="file_hash",    dtype=DataType.VARCHAR,      max_length=64),
            FieldSchema(name="url",          dtype=DataType.VARCHAR,      max_length=512),
            FieldSchema(name="chunk_index",  dtype=DataType.INT64),
            FieldSchema(name="parent_index", dtype=DataType.INT64),
            FieldSchema(name="child_index",  dtype=DataType.INT64),
            FieldSchema(name="parent_type",  dtype=DataType.VARCHAR,      max_length=64),
            FieldSchema(name="parent_title", dtype=DataType.VARCHAR,      max_length=512),
            FieldSchema(name="text",         dtype=DataType.VARCHAR,      max_length=65535),
            FieldSchema(name="embedding",    dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
            FieldSchema(name="article_title",   dtype=DataType.VARCHAR,      max_length=1024),
        ]
        schema     = CollectionSchema(fields=fields, description="Lovdata Norwegian Legal Documents")
        collection = Collection(name=self.collection_name, schema=schema)

        collection.create_index(
            field_name="embedding",
            index_params={
                "index_type": "HNSW",
                "metric_type": "COSINE",
                "params": {"M": 8, "efConstruction": 200},
            },
        )
        collection.load()
        logger.info(f"✅ Collection created and loaded: {self.collection_name}")
        return collection

    # ------------------------------------------------------------------
    # INSERT — CPU-aware sub-batches (all sizes from config)
    # ------------------------------------------------------------------
    def insert_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not chunks:
            return {"inserted": 0}

        self._ensure_connection()
        if self.collection is None:
            raise RuntimeError("Milvus collection not initialised")

        # Normalise all embeddings upfront
        normalized = []
        for i, c in enumerate(chunks):
            try:
                normalized.append({
                    "chunk_id":     c.get("chunk_id") or c.get("stable_chunk_id"),
                    "file_name":    c["file_name"],
                    "file_hash":    c["file_hash"],
                    "url":          c.get("url", ""),
                    "chunk_index":  c["chunk_index"],
                    "parent_index": c.get("parent_index", 0),
                    "child_index":  c.get("child_index", 0),
                    "parent_type":  c.get("section_type") or c.get("parent_type") or "document",
                    "parent_title": c.get("section_title") or c.get("parent_title") or "",
                    "article_title": c.get("article_title") or c.get("section_title") or "",
                    "text":         c["text"],
                    "embedding":    self._fix_embedding(c["embedding"]),
                })
            except Exception as e:
                logger.error(f"Failed to normalise chunk {i}: {e}")
                raise

        total_rows     = len(normalized)
        total_inserted = 0
        all_pk         = []

        logger.info(
            f"[Milvus] Inserting {total_rows} rows | "
            f"sub-batch={MILVUS_INSERT_BATCH} | "
            f"sleep={MILVUS_INSERT_SLEEP}s | "
            f"cpu-threshold={MILVUS_CPU_PAUSE_THRESHOLD}%"
        )

        for batch_start in range(0, total_rows, MILVUS_INSERT_BATCH):
            batch     = normalized[batch_start: batch_start + MILVUS_INSERT_BATCH]
            batch_num = batch_start // MILVUS_INSERT_BATCH + 1

            # Wait for CPU to cool before each sub-batch
            _wait_for_cpu(
                threshold=MILVUS_CPU_PAUSE_THRESHOLD,
                max_wait=MILVUS_CPU_MAX_WAIT,
                label=f"sub-batch {batch_num}",
            )

            data = [
                [c["chunk_id"]     for c in batch],
                [c["file_name"]    for c in batch],
                [c["file_hash"]    for c in batch],
                [c["url"]          for c in batch],
                [c["chunk_index"]  for c in batch],
                [c["parent_index"] for c in batch],
                [c["child_index"]  for c in batch],
                [c["parent_type"]  for c in batch],
                [c["parent_title"] for c in batch],
                [c["text"]         for c in batch],
                [c["embedding"]    for c in batch],
                [c["article_title"] for c in batch],
            ]

            payload_mb = sys.getsizeof(data) / (1024 * 1024)
            self._log_system_state("INSERT_START", len(batch), payload_mb)

            start = time.time()
            try:
                result  = self.collection.insert(data)
                elapsed = time.time() - start
                logger.info(
                    f"[Milvus] Sub-batch {batch_num}: "
                    f"{len(batch)} rows in {elapsed:.2f}s"
                )
                total_inserted += len(batch)
                all_pk.extend(result.primary_keys)

            except Exception as e:
                elapsed = time.time() - start
                logger.error(
                    f"[Milvus INSERT_FAILED] sub-batch={batch_num} "
                    f"time={elapsed:.2f}s error={e}"
                )
                raise

            self.insert_counter += len(batch)

            # Periodic flush (interval from config)
            if self.insert_counter % MILVUS_FLUSH_EVERY == 0:
                logger.info("🔄 Periodic Milvus flush...")
                self.collection.flush()

            # Sleep between sub-batches (skip after the last one)
            if batch_start + MILVUS_INSERT_BATCH < total_rows:
                time.sleep(MILVUS_INSERT_SLEEP)

        logger.info(f"[Milvus] ✅ Total inserted: {total_inserted}/{total_rows}")
        return {"inserted": total_inserted, "milvus_ids": all_pk}

    def close(self):
        if self._connected:
            logger.info("🔄 Final Milvus flush before close...")
            if hasattr(self, "collection") and self.collection is not None:
                try:
                    self.collection.flush()
                except Exception as e:
                    logger.warning(f"Flush failed during close: {e}")
            connections.disconnect("default")
            self._connected = False