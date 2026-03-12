### This code defines the MilvusTextStore class, which provides a CPU-aware interface for inserting text chunks with embeddings into a Milvus vector database. It includes logic to delete stale rows based on file_hash before inserting fresh data, and it batches inserts while monitoring CPU usage to avoid overloading the system. All tuning parameters are imported from a config module, and detailed logging is included for monitoring the insertion process and system state.
# """
# MilvusTextStore — CPU-aware version
# =====================================
# All tuning constants are imported from config.py (which reads .env).
# No os.getenv calls or numeric literals appear in this file.
# """

# import logging
# import sys
# import time
# import psutil

# from ingestion.src.storage.supabase_store import SupabaseStore
# from ingestion.src.config import (
#     MILVUS_HOST,
#     MILVUS_PORT,
#     MILVUS_COLLECTION,
#     MILVUS_DIMENSION,
#     MILVUS_CONNECT_TIMEOUT,
#     MILVUS_INSERT_BATCH,
#     MILVUS_INSERT_SLEEP,
#     MILVUS_FLUSH_EVERY,
#     MILVUS_CPU_PAUSE_THRESHOLD,
#     MILVUS_CPU_MAX_WAIT,
# )

# from typing import List, Dict, Any

# from pymilvus import (
#     connections,
#     Collection,
#     CollectionSchema,
#     FieldSchema,
#     DataType,
#     utility,
# )

# logger = logging.getLogger(__name__)


# def _wait_for_cpu(threshold: int, max_wait: int, label: str = "") -> None:
#     """Block until CPU% drops below threshold or max_wait seconds elapsed."""
#     waited = 0
#     while waited < max_wait:
#         cpu = psutil.cpu_percent(interval=1)
#         if cpu < threshold:
#             return
#         logger.warning(
#             f"⏳ Milvus: CPU {cpu}% > {threshold}% [{label}] — waiting 3s"
#         )
#         time.sleep(3)
#         waited += 3
#     logger.warning(f"⚠️  CPU still elevated after {max_wait}s — proceeding")


# class MilvusTextStore:
#     def __init__(self):
#         self.collection_name = MILVUS_COLLECTION
#         self.embedding_dim   = MILVUS_DIMENSION
#         self._connected      = False
#         self.collection      = None
#         self.insert_counter  = 0

#     def _ensure_connection(self):
#         if not self._connected:
#             connections.connect(
#                 alias="default",
#                 host=MILVUS_HOST,
#                 port=MILVUS_PORT,
#                 timeout=MILVUS_CONNECT_TIMEOUT,
#             )
#             self.collection = self._get_or_create_collection()
#             self._connected = True

#     def delete_by_file_name(self, file_name: str):
#         self._ensure_connection()
#         self.collection.delete(f'file_name == "{file_name}"')
#         self.collection.flush()

#     # ------------------------------------------------------------------
#     # Embedding normalisation
#     # ------------------------------------------------------------------
#     def _fix_embedding(self, emb):
#         if isinstance(emb, dict):
#             emb = (
#                 emb.get("dense_vecs")
#                 or emb.get("embedding")
#                 or emb.get("vector")
#             )
#             if emb is None:
#                 raise ValueError("Could not extract embedding from dict")

#         if hasattr(emb, "tolist"):
#             emb = emb.tolist()

#         while isinstance(emb, list) and len(emb) > 0 and isinstance(emb[0], list):
#             emb = emb[0]

#         if not isinstance(emb, list):
#             raise TypeError(f"Embedding must be a list, got {type(emb)}")
#         if not emb:
#             raise ValueError("Embedding is empty")

#         result = [float(x) for x in emb]

#         if len(result) != self.embedding_dim:
#             raise ValueError(
#                 f"Embedding dimension mismatch: "
#                 f"expected {self.embedding_dim}, got {len(result)}"
#             )
#         return result

#     # ------------------------------------------------------------------
#     # System state logging
#     # ------------------------------------------------------------------
#     def _log_system_state(self, stage: str, rows: int, payload_mb: float):
#         cpu = psutil.cpu_percent()
#         mem = psutil.virtual_memory().percent
#         logger.info(
#             f"[Milvus {stage}] rows={rows} | payload={payload_mb:.2f}MB "
#             f"| cpu={cpu}% | mem={mem}%"
#         )

#     # ------------------------------------------------------------------
#     # Collection (create or load)
#     # ------------------------------------------------------------------
#     def _get_or_create_collection(self) -> Collection:
#         if utility.has_collection(self.collection_name):
#             logger.info(f"✅ Loading existing collection: {self.collection_name}")
#             col = Collection(self.collection_name)
#             col.load()
#             return col

#         logger.info(f"🔨 Creating collection: {self.collection_name}")
#         fields = [
#             FieldSchema(name="id",           dtype=DataType.INT64,        is_primary=True, auto_id=True),
#             FieldSchema(name="chunk_id",     dtype=DataType.VARCHAR,      max_length=128),
#             FieldSchema(name="file_name",    dtype=DataType.VARCHAR,      max_length=255),
#             FieldSchema(name="file_hash",    dtype=DataType.VARCHAR,      max_length=64),
#             FieldSchema(name="url",          dtype=DataType.VARCHAR,      max_length=512),
#             FieldSchema(name="chunk_index",  dtype=DataType.INT64),
#             FieldSchema(name="parent_index", dtype=DataType.INT64),
#             FieldSchema(name="child_index",  dtype=DataType.INT64),
#             FieldSchema(name="parent_type",  dtype=DataType.VARCHAR,      max_length=64),
#             FieldSchema(name="parent_title", dtype=DataType.VARCHAR,      max_length=512),
#             FieldSchema(name="text",         dtype=DataType.VARCHAR,      max_length=65535),
#             FieldSchema(name="embedding",    dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
#             FieldSchema(name="article_title",   dtype=DataType.VARCHAR,      max_length=1024),
#         ]
#         schema     = CollectionSchema(fields=fields, description="Lovdata Norwegian Legal Documents")
#         collection = Collection(name=self.collection_name, schema=schema)

#         collection.create_index(
#             field_name="embedding",
#             index_params={
#                 "index_type": "HNSW",
#                 "metric_type": "COSINE",
#                 "params": {"M": 8, "efConstruction": 200},
#             },
#         )
#         collection.load()
#         logger.info(f"✅ Collection created and loaded: {self.collection_name}")
#         return collection

#     # ------------------------------------------------------------------
#     # INSERT — CPU-aware sub-batches (all sizes from config)
#     # ------------------------------------------------------------------
#     def insert_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
#         if not chunks:
#             return {"inserted": 0}

#         self._ensure_connection()
#         if self.collection is None:
#             raise RuntimeError("Milvus collection not initialised")

#         # Normalise all embeddings upfront
#         normalized = []
#         for i, c in enumerate(chunks):
#             try:
#                 normalized.append({
#                     "chunk_id":     c.get("chunk_id") or c.get("stable_chunk_id"),
#                     "file_name":    c["file_name"],
#                     "file_hash":    c["file_hash"],
#                     "url":          c.get("url", ""),
#                     "chunk_index":  c["chunk_index"],
#                     "parent_index": c.get("parent_index", 0),
#                     "child_index":  c.get("child_index", 0),
#                     "parent_type":  c.get("section_type") or c.get("parent_type") or "document",
#                     "parent_title": c.get("section_title") or c.get("parent_title") or "",
#                     "article_title": c.get("article_title") or c.get("section_title") or "",
#                     "text":         c["text"],
#                     "embedding":    self._fix_embedding(c["embedding"]),
#                 })
#             except Exception as e:
#                 logger.error(f"Failed to normalise chunk {i}: {e}")
#                 raise

#         total_rows     = len(normalized)
#         total_inserted = 0
#         all_pk         = []

#         logger.info(
#             f"[Milvus] Inserting {total_rows} rows | "
#             f"sub-batch={MILVUS_INSERT_BATCH} | "
#             f"sleep={MILVUS_INSERT_SLEEP}s | "
#             f"cpu-threshold={MILVUS_CPU_PAUSE_THRESHOLD}%"
#         )

#         for batch_start in range(0, total_rows, MILVUS_INSERT_BATCH):
#             batch     = normalized[batch_start: batch_start + MILVUS_INSERT_BATCH]
#             batch_num = batch_start // MILVUS_INSERT_BATCH + 1

#             # Wait for CPU to cool before each sub-batch
#             _wait_for_cpu(
#                 threshold=MILVUS_CPU_PAUSE_THRESHOLD,
#                 max_wait=MILVUS_CPU_MAX_WAIT,
#                 label=f"sub-batch {batch_num}",
#             )

#             data = [
#                 [c["chunk_id"]     for c in batch],
#                 [c["file_name"]    for c in batch],
#                 [c["file_hash"]    for c in batch],
#                 [c["url"]          for c in batch],
#                 [c["chunk_index"]  for c in batch],
#                 [c["parent_index"] for c in batch],
#                 [c["child_index"]  for c in batch],
#                 [c["parent_type"]  for c in batch],
#                 [c["parent_title"] for c in batch],
#                 [c["text"]         for c in batch],
#                 [c["embedding"]    for c in batch],
#                 [c["article_title"] for c in batch],
#             ]

#             payload_mb = sys.getsizeof(data) / (1024 * 1024)
#             self._log_system_state("INSERT_START", len(batch), payload_mb)

#             start = time.time()
#             try:
#                 result  = self.collection.insert(data)
#                 elapsed = time.time() - start
#                 logger.info(
#                     f"[Milvus] Sub-batch {batch_num}: "
#                     f"{len(batch)} rows in {elapsed:.2f}s"
#                 )
#                 total_inserted += len(batch)
#                 all_pk.extend(result.primary_keys)

#             except Exception as e:
#                 elapsed = time.time() - start
#                 logger.error(
#                     f"[Milvus INSERT_FAILED] sub-batch={batch_num} "
#                     f"time={elapsed:.2f}s error={e}"
#                 )
#                 raise

#             self.insert_counter += len(batch)

#             # Periodic flush (interval from config)
#             if self.insert_counter % MILVUS_FLUSH_EVERY == 0:
#                 logger.info("🔄 Periodic Milvus flush...")
#                 self.collection.flush()

#             # Sleep between sub-batches (skip after the last one)
#             if batch_start + MILVUS_INSERT_BATCH < total_rows:
#                 time.sleep(MILVUS_INSERT_SLEEP)

#         logger.info(f"[Milvus] ✅ Total inserted: {total_inserted}/{total_rows}")
#         return {"inserted": total_inserted, "milvus_ids": all_pk}

#     def close(self):
#         if self._connected:
#             logger.info("🔄 Final Milvus flush before close...")
#             if hasattr(self, "collection") and self.collection is not None:
#                 try:
#                     self.collection.flush()
#                 except Exception as e:
#                     logger.warning(f"Flush failed during close: {e}")
#             connections.disconnect("default")
#             self._connected = False
#------------------------------------------------------------------

"""
storage/milvus_store.py
========================
Milvus vector store with CPU-aware insert batching.

Re-ingestion strategy: DELETE old rows for a file_hash first, then INSERT
fresh rows with updated metadata. Milvus has no UPDATE — delete + re-insert
is the correct approach.
"""

import logging
import sys
import time
from typing import Any, Dict, List

import psutil
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from ingestion.src.config import (
    MILVUS_COLLECTION,
    MILVUS_CONNECT_TIMEOUT,
    MILVUS_CPU_MAX_WAIT,
    MILVUS_CPU_PAUSE_THRESHOLD,
    MILVUS_DIMENSION,
    MILVUS_FLUSH_EVERY,
    MILVUS_HOST,
    MILVUS_INSERT_BATCH,
    MILVUS_INSERT_SLEEP,
    MILVUS_PORT,
)

logger = logging.getLogger(__name__)


def _wait_for_cpu(threshold: int, max_wait: int, label: str = "") -> None:
    waited = 0
    while waited < max_wait:
        cpu = psutil.cpu_percent(interval=1)
        if cpu < threshold:
            return
        logger.warning(f"Milvus: CPU {cpu}% > {threshold}% [{label}] — waiting 3s")
        time.sleep(3)
        waited += 3
    logger.warning(f"CPU still elevated after {max_wait}s — proceeding")


class MilvusTextStore:

    def __init__(self) -> None:
        self.collection_name = MILVUS_COLLECTION
        self.embedding_dim   = MILVUS_DIMENSION
        self._connected      = False
        self.collection      = None
        self.insert_counter  = 0

    def _ensure_connection(self) -> None:
        if not self._connected:
            connections.connect(
                alias="default",
                host=MILVUS_HOST,
                port=MILVUS_PORT,
                timeout=MILVUS_CONNECT_TIMEOUT,
            )
            self.collection = self._get_or_create_collection()
            self._connected = True

    def _fix_embedding(self, emb: Any) -> List[float]:
        if isinstance(emb, dict):
            emb = emb.get("dense_vecs") or emb.get("embedding") or emb.get("vector")
            if emb is None:
                raise ValueError("Could not extract embedding from dict")
        if hasattr(emb, "tolist"):
            emb = emb.tolist()
        while isinstance(emb, list) and emb and isinstance(emb[0], list):
            emb = emb[0]
        if not isinstance(emb, list):
            raise TypeError(f"Embedding must be a list, got {type(emb)}")
        if not emb:
            raise ValueError("Embedding is empty")
        result = [float(x) for x in emb]
        if len(result) != self.embedding_dim:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.embedding_dim}, "
                f"got {len(result)}"
            )
        return result

    def _get_or_create_collection(self) -> Collection:
        if utility.has_collection(self.collection_name):
            logger.info(f"Loading existing collection: {self.collection_name}")
            col = Collection(self.collection_name)
            col.load()
            return col

        logger.info(f"Creating collection: {self.collection_name}")
        fields = [
            FieldSchema(name="milvus_id",       dtype=DataType.INT64,   is_primary=True, auto_id=True),
            FieldSchema(name="chunk_id",         dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="file_hash",        dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="domain_name",      dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="sub_domain_name",  dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="tags",             dtype=DataType.VARCHAR, max_length=4096),
            FieldSchema(name="jurisdiction",     dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="statute_id",       dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="tier",             dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="source_type",      dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="chunk_index",      dtype=DataType.INT64),
            FieldSchema(name="parent_index",     dtype=DataType.INT64),
            FieldSchema(name="child_index",      dtype=DataType.INT64),
            FieldSchema(name="text",             dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="parent_title",     dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="law_short_name",   dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="paragraph_number", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="embedding",        dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
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
        logger.info(f"Collection created and loaded: {self.collection_name}")
        return collection

    def insert_chunks(
        self,
        chunks:   List[Dict[str, Any]],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not chunks:
            return {"inserted": 0}

        self._ensure_connection()
        if self.collection is None:
            raise RuntimeError("Milvus collection not initialised")

        file_hash = chunks[0]["file_hash"]

        # Delete stale rows before inserting fresh ones
        try:
            existing = self.collection.query(
                expr=f'file_hash == "{file_hash}"',
                output_fields=["milvus_id"],
            )
            if existing:
                self.collection.delete(f'file_hash == "{file_hash}"')
                self.collection.flush()
                logger.info(
                    f"  Deleted {len(existing)} stale row(s) for "
                    f"file_hash={file_hash[:8]}..."
                )
        except Exception as exc:
            logger.warning(f"  Could not delete stale rows: {exc}")

        # Normalise all chunks upfront
        normalized = []
        for i, c in enumerate(chunks):
            try:
                normalized.append({
                    "chunk_id":         c.get("chunk_id", ""),
                    "file_hash":        c["file_hash"],
                    "domain_name":      metadata.get("domain_name",     ""),
                    "sub_domain_name":  metadata.get("sub_domain_name", ""),
                    "tags":             (
                        ",".join(metadata.get("tags"))
                        if isinstance(metadata.get("tags"), list)
                        else metadata.get("tags", "")
                    ),
                    "jurisdiction":     metadata.get("jurisdiction",    ""),
                    "statute_id":       metadata.get("statute_id",      ""),
                    "tier":             metadata.get("tier",            ""),
                    "source_type":      metadata.get("source_type",     ""),
                    "chunk_index":      c.get("chunk_index", c.get("child_index", 0)),
                    "parent_index":     c.get("parent_index",  0),
                    "child_index":      c.get("child_index",   0),
                    "text":             (c.get("text")             or "")[:65000],
                    "parent_title":     (c.get("parent_title")     or "")[:512],
                    "law_short_name":   (c.get("law_short_name")   or "")[:256],
                    "paragraph_number": (c.get("paragraph_number") or "")[:64],
                    "embedding":        self._fix_embedding(c["embedding"]),
                })
            except Exception as exc:
                logger.error(f"Failed to normalise chunk {i}: {exc}")
                raise

        total_rows     = len(normalized)
        total_inserted = 0
        all_pk: List   = []

        logger.info(
            f"Inserting {total_rows} row(s) into Milvus | "
            f"sub-batch={MILVUS_INSERT_BATCH}"
        )

        for batch_start in range(0, total_rows, MILVUS_INSERT_BATCH):
            batch     = normalized[batch_start: batch_start + MILVUS_INSERT_BATCH]
            batch_num = batch_start // MILVUS_INSERT_BATCH + 1

            _wait_for_cpu(
                threshold=MILVUS_CPU_PAUSE_THRESHOLD,
                max_wait=MILVUS_CPU_MAX_WAIT,
                label=f"sub-batch {batch_num}",
            )

            data = [
                [c["chunk_id"]         for c in batch],
                [c["file_hash"]        for c in batch],
                [c["domain_name"]      for c in batch],
                [c["sub_domain_name"]  for c in batch],
                [c["tags"]             for c in batch],
                [c["jurisdiction"]     for c in batch],
                [c["statute_id"]       for c in batch],
                [c["tier"]             for c in batch],
                [c["source_type"]      for c in batch],
                [c["chunk_index"]      for c in batch],
                [c["parent_index"]     for c in batch],
                [c["child_index"]      for c in batch],
                [c["text"]             for c in batch],
                [c["parent_title"]     for c in batch],
                [c["law_short_name"]   for c in batch],
                [c["paragraph_number"] for c in batch],
                [c["embedding"]        for c in batch],
            ]

            payload_mb = sys.getsizeof(data) / (1024 * 1024)
            cpu        = psutil.cpu_percent()
            mem        = psutil.virtual_memory().percent
            logger.info(
                f"  Batch {batch_num}: {len(batch)} rows | "
                f"payload={payload_mb:.2f}MB | cpu={cpu}% | mem={mem}%"
            )

            start = time.time()
            try:
                result = self.collection.insert(data)
                elapsed = time.time() - start
                logger.info(f"  Batch {batch_num}: inserted in {elapsed:.2f}s")
                total_inserted += len(batch)
                all_pk.extend(result.primary_keys)
            except Exception as exc:
                elapsed = time.time() - start
                logger.error(
                    f"  Batch {batch_num} INSERT FAILED after {elapsed:.2f}s: {exc}"
                )
                raise

            self.insert_counter += len(batch)
            if self.insert_counter % MILVUS_FLUSH_EVERY == 0:
                logger.info("Periodic Milvus flush...")
                self.collection.flush()

            if batch_start + MILVUS_INSERT_BATCH < total_rows:
                time.sleep(MILVUS_INSERT_SLEEP)

        logger.info(f"Milvus insert complete: {total_inserted}/{total_rows} row(s)")
        return {"inserted": total_inserted, "milvus_ids": all_pk}

    def close(self) -> None:
        if self._connected:
            logger.info("Final Milvus flush before close...")
            if self.collection is not None:
                try:
                    self.collection.flush()
                except Exception as exc:
                    logger.warning(f"Flush failed during close: {exc}")
            connections.disconnect("default")
            self._connected = False