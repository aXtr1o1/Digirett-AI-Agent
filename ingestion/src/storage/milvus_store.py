# from __future__ import annotations

# import logging
# import sys
# import time
# from typing import Any, Dict, List

# import psutil
# from pymilvus import (
#     Collection,
#     CollectionSchema,
#     DataType,
#     FieldSchema,
#     connections,
#     utility,
# )

# from ingestion.src.config import (
#     MILVUS_COLLECTION,
#     MILVUS_CONNECT_TIMEOUT,
#     MILVUS_CPU_MAX_WAIT,
#     MILVUS_CPU_PAUSE_THRESHOLD,
#     MILVUS_DIMENSION,
#     MILVUS_FLUSH_EVERY,
#     MILVUS_HOST,
#     MILVUS_INSERT_BATCH,
#     MILVUS_INSERT_SLEEP,
#     MILVUS_PORT,
# )

# logger = logging.getLogger(__name__)


# def _wait_for_cpu(threshold: int, max_wait: int, label: str = "") -> None:
#     waited = 0
#     while waited < max_wait:
#         cpu = psutil.cpu_percent(interval=1)
#         if cpu < threshold:
#             return
#         logger.warning(
#             f"Milvus CPU {cpu}% > {threshold}% [{label}] — waiting 3s"
#         )
#         time.sleep(3)
#         waited += 3
#     logger.warning(f"CPU still elevated after {max_wait}s — proceeding")


# class MilvusTextStore:
#     def __init__(self) -> None:
#         self.collection_name = MILVUS_COLLECTION
#         self.embedding_dim = MILVUS_DIMENSION
#         self._connected = False
#         self.collection: Collection | None = None
#         self.insert_counter = 0

#     def _ensure_connection(self) -> None:
#         if not self._connected:
#             connections.connect(
#                 alias="default",
#                 host=MILVUS_HOST,
#                 port=MILVUS_PORT,
#                 timeout=MILVUS_CONNECT_TIMEOUT,
#             )
#             self.collection = self._get_or_create_collection()
#             self._connected = True

#     def _fix_embedding(self, emb: Any) -> List[float]:
#         if isinstance(emb, dict):
#             emb = emb.get("dense_vecs") or emb.get("embedding") or emb.get("vector")
#             if emb is None:
#                 raise ValueError("Could not extract embedding from dict")

#         if hasattr(emb, "tolist"):
#             emb = emb.tolist()

#         while isinstance(emb, list) and emb and isinstance(emb[0], list):
#             emb = emb[0]

#         if not isinstance(emb, list):
#             raise TypeError(f"Embedding must be a list, got {type(emb)}")
#         if not emb:
#             raise ValueError("Embedding is empty")

#         result = [float(x) for x in emb]
#         if len(result) != self.embedding_dim:
#             raise ValueError(
#                 f"Embedding dimension mismatch: expected {self.embedding_dim}, got {len(result)}"
#             )
#         return result

#     def _get_or_create_collection(self) -> Collection:
#         if utility.has_collection(self.collection_name):
#             logger.info(f"Loading existing collection: {self.collection_name}")
#             collection = Collection(self.collection_name)
#             collection.load()
#             return collection

#         logger.info(f"Creating collection: {self.collection_name}")
#         fields = [
#             FieldSchema(
#                 name="milvus_id",
#                 dtype=DataType.INT64,
#                 is_primary=True,
#                 auto_id=True,
#             ),
#             FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=255),
#             FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=255),
#             FieldSchema(name="source_doc_url", dtype=DataType.VARCHAR, max_length=1024),
#             FieldSchema(name="section_ref", dtype=DataType.VARCHAR, max_length=128),
#             FieldSchema(name="domain", dtype=DataType.VARCHAR, max_length=512),
#             FieldSchema(name="subdomain", dtype=DataType.VARCHAR, max_length=1024),
#             FieldSchema(name="b2b_b2c", dtype=DataType.VARCHAR, max_length=32),
#             FieldSchema(name="tier", dtype=DataType.VARCHAR, max_length=64),
#             FieldSchema(name="jurisdiction", dtype=DataType.VARCHAR, max_length=64),
#             FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
#             FieldSchema(
#                 name="embedding",
#                 dtype=DataType.FLOAT_VECTOR,
#                 dim=self.embedding_dim,
#             ),
#         ]

#         schema = CollectionSchema(
#             fields=fields,
#             description="Validated DigiRett legal chunks",
#         )
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
#         logger.info(f"Collection created and loaded: {self.collection_name}")
#         return collection

#     def delete_by_document_id(self, document_id: str) -> None:
#         self._ensure_connection()
#         if self.collection is None:
#             raise RuntimeError("Milvus collection not initialised")

#         try:
#             self.collection.delete(f'document_id == "{document_id}"')
#             self.collection.flush()
#             logger.info(f"Deleted old rows for document_id={document_id}")
#         except Exception as exc:
#             logger.warning(f"Could not delete rows for document_id={document_id}: {exc}")

#     def insert_chunks(
#         self,
#         chunks: List[Dict[str, Any]],
#         metadata: Dict[str, Any],
#     ) -> Dict[str, Any]:
#         if not chunks:
#             return {"inserted": 0}

#         self._ensure_connection()
#         if self.collection is None:
#             raise RuntimeError("Milvus collection not initialised")

#         required_metadata = [
#             "document_id",
#             "source_doc_url",
#             "section_ref",
#             "domain",
#             "subdomain",
#             "b2b_b2c",
#             "tier",
#             "jurisdiction",
#         ]
#         missing = [k for k in required_metadata if not metadata.get(k)]
#         if missing:
#             raise ValueError(f"Missing Milvus metadata fields: {missing}")

#         document_id = metadata["document_id"]

#         # Re-ingestion strategy: delete old rows for this document_id, then re-insert.
#         try:
#             existing = self.collection.query(
#                 expr=f'document_id == "{document_id}"',
#                 output_fields=["milvus_id"],
#             )
#             if existing:
#                 self.collection.delete(f'document_id == "{document_id}"')
#                 self.collection.flush()
#                 logger.info(
#                     f"Deleted {len(existing)} stale row(s) for document_id={document_id}"
#                 )
#         except Exception as exc:
#             logger.warning(f"Could not delete stale rows for {document_id}: {exc}")

#         normalized: List[Dict[str, Any]] = []
#         for i, chunk in enumerate(chunks):
#             try:
#                 normalized.append(
#                     {
#                         "chunk_id": str(chunk["chunk_id"]),
#                         "document_id": document_id,
#                         "source_doc_url": str(metadata["source_doc_url"]),
#                         "section_ref": str(metadata["section_ref"]),
#                         "domain": str(metadata["domain"]),
#                         "subdomain": str(metadata["subdomain"]),
#                         "b2b_b2c": str(metadata["b2b_b2c"]),
#                         "tier": str(metadata["tier"]),
#                         "jurisdiction": str(metadata["jurisdiction"]),
#                         "text": (chunk.get("text") or "")[:65000],
#                         "embedding": self._fix_embedding(chunk["embedding"]),
#                     }
#                 )
#             except Exception as exc:
#                 logger.error(f"Failed to normalise chunk {i}: {exc}")
#                 raise

#         total_rows = len(normalized)
#         total_inserted = 0
#         all_pk: List[int] = []

#         logger.info(
#             f"Inserting {total_rows} row(s) into Milvus | "
#             f"sub-batch={MILVUS_INSERT_BATCH}"
#         )

#         for batch_start in range(0, total_rows, MILVUS_INSERT_BATCH):
#             batch = normalized[batch_start : batch_start + MILVUS_INSERT_BATCH]
#             batch_num = batch_start // MILVUS_INSERT_BATCH + 1

#             _wait_for_cpu(
#                 threshold=MILVUS_CPU_PAUSE_THRESHOLD,
#                 max_wait=MILVUS_CPU_MAX_WAIT,
#                 label=f"sub-batch {batch_num}",
#             )

#             data = [
#                 [c["chunk_id"] for c in batch],
#                 [c["document_id"] for c in batch],
#                 [c["source_doc_url"] for c in batch],
#                 [c["section_ref"] for c in batch],
#                 [c["domain"] for c in batch],
#                 [c["subdomain"] for c in batch],
#                 [c["b2b_b2c"] for c in batch],
#                 [c["tier"] for c in batch],
#                 [c["jurisdiction"] for c in batch],
#                 [c["text"] for c in batch],
#                 [c["embedding"] for c in batch],
#             ]

#             payload_mb = sys.getsizeof(data) / (1024 * 1024)
#             cpu = psutil.cpu_percent()
#             mem = psutil.virtual_memory().percent
#             logger.info(
#                 f"Batch {batch_num}: {len(batch)} rows | "
#                 f"payload={payload_mb:.2f}MB | cpu={cpu}% | mem={mem}%"
#             )

#             start = time.time()
#             try:
#                 result = self.collection.insert(data)
#                 elapsed = time.time() - start
#                 logger.info(f"Batch {batch_num}: inserted in {elapsed:.2f}s")
#                 total_inserted += len(batch)
#                 all_pk.extend(result.primary_keys)
#             except Exception as exc:
#                 elapsed = time.time() - start
#                 logger.error(
#                     f"Batch {batch_num} INSERT FAILED after {elapsed:.2f}s: {exc}"
#                 )
#                 raise

#             self.insert_counter += len(batch)
#             if self.insert_counter % MILVUS_FLUSH_EVERY == 0:
#                 logger.info("Periodic Milvus flush...")
#                 self.collection.flush()

#             if batch_start + MILVUS_INSERT_BATCH < total_rows:
#                 time.sleep(MILVUS_INSERT_SLEEP)

#         logger.info(f"Milvus insert complete: {total_inserted}/{total_rows} row(s)")
#         return {"inserted": total_inserted, "milvus_ids": all_pk}

#     def close(self) -> None:
#         if self._connected:
#             logger.info("Final Milvus flush before close...")
#             if self.collection is not None:
#                 try:
#                     self.collection.flush()
#                 except Exception as exc:
#                     logger.warning(f"Flush failed during close: {exc}")
#             connections.disconnect("default")
#             self._connected = False

"""
storage/milvus_store.py
=======================

Lean production Milvus store for validated DigiRett ingestion.

One row per chunk.

Stored fields:
- chunk_id
- source_id
- document_id
- text
- embedding
- source_doc_url
- source_url
- section_ref
- domain
- subdomain
- b2b_b2c
- tier
- jurisdiction
"""

from __future__ import annotations

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
        logger.warning(
            f"Milvus CPU {cpu}% > {threshold}% [{label}] — waiting 3s"
        )
        time.sleep(3)
        waited += 3
    logger.warning(f"CPU still elevated after {max_wait}s — proceeding")


class MilvusTextStore:
    def __init__(self) -> None:
        self.collection_name = MILVUS_COLLECTION
        self.embedding_dim = MILVUS_DIMENSION
        self._connected = False
        self.collection: Collection | None = None
        self.insert_counter = 0

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
                f"Embedding dimension mismatch: expected {self.embedding_dim}, got {len(result)}"
            )
        return result

    def _get_or_create_collection(self) -> Collection:
        if utility.has_collection(self.collection_name):
            logger.info(f"Loading existing collection: {self.collection_name}")
            collection = Collection(self.collection_name)
            collection.load()
            return collection

        logger.info(f"Creating collection: {self.collection_name}")
        fields = [
            FieldSchema(
                name="milvus_id",
                dtype=DataType.INT64,
                is_primary=True,
                auto_id=True,
            ),
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="source_id", dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="source_doc_url", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="section_ref", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="source_url", dtype=DataType.VARCHAR, max_length=1024),  # ADDED
            FieldSchema(name="domain", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="subdomain", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="b2b_b2c", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="tier", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="jurisdiction", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(
                name="embedding",
                dtype=DataType.FLOAT_VECTOR,
                dim=self.embedding_dim,
            ),
        ]

        schema = CollectionSchema(
            fields=fields,
            description="Validated DigiRett legal chunks",
        )
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

    def delete_by_document_id(self, document_id: str) -> None:
        self._ensure_connection()
        if self.collection is None:
            raise RuntimeError("Milvus collection not initialised")

        try:
            self.collection.delete(f'document_id == "{document_id}"')
            self.collection.flush()
            logger.info(f"Deleted old rows for document_id={document_id}")
        except Exception as exc:
            logger.warning(f"Could not delete rows for document_id={document_id}: {exc}")

    def insert_chunks(
        self,
        chunks: List[Dict[str, Any]],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not chunks:
            return {"inserted": 0}

        self._ensure_connection()
        if self.collection is None:
            raise RuntimeError("Milvus collection not initialised")

        required_metadata = [
            "document_id",
            "source_id",
            "source_doc_url",
            "section_ref",
            "domain",
            "subdomain",
            "b2b_b2c",
            "tier",
            "jurisdiction",
        ]
        missing = [k for k in required_metadata if not metadata.get(k)]
        if missing:
            raise ValueError(f"Missing Milvus metadata fields: {missing}")

        document_id = metadata["document_id"]

        # Re-ingestion strategy: delete old rows for this document_id, then re-insert.
        try:
            existing = self.collection.query(
                expr=f'document_id == "{document_id}"',
                output_fields=["milvus_id"],
            )
            if existing:
                self.collection.delete(f'document_id == "{document_id}"')
                self.collection.flush()
                logger.info(
                    f"Deleted {len(existing)} stale row(s) for document_id={document_id}"
                )
        except Exception as exc:
            logger.warning(f"Could not delete stale rows for {document_id}: {exc}")

        normalized: List[Dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            try:
                normalized.append(
                    {
                        "chunk_id": str(chunk["chunk_id"]),
                        "source_id": str(metadata.get("source_id", "")),
                        "document_id": document_id,
                        "source_doc_url": str(metadata["source_doc_url"]),
                        "section_ref": str(metadata["section_ref"]),
                        "source_url": str(chunk.get("source_url", "")),  # ADDED
                        "domain": str(metadata["domain"]),
                        "subdomain": str(metadata["subdomain"]),
                        "b2b_b2c": str(metadata["b2b_b2c"]),
                        "tier": str(metadata["tier"]),
                        "jurisdiction": str(metadata["jurisdiction"]),
                        "text": (chunk.get("text") or "")[:65000],
                        "embedding": self._fix_embedding(chunk["embedding"]),
                    }
                )
            except Exception as exc:
                logger.error(f"Failed to normalise chunk {i}: {exc}")
                raise

        total_rows = len(normalized)
        total_inserted = 0
        all_pk: List[int] = []

        logger.info(
            f"Inserting {total_rows} row(s) into Milvus | "
            f"sub-batch={MILVUS_INSERT_BATCH}"
        )

        for batch_start in range(0, total_rows, MILVUS_INSERT_BATCH):
            batch = normalized[batch_start : batch_start + MILVUS_INSERT_BATCH]
            batch_num = batch_start // MILVUS_INSERT_BATCH + 1

            _wait_for_cpu(
                threshold=MILVUS_CPU_PAUSE_THRESHOLD,
                max_wait=MILVUS_CPU_MAX_WAIT,
                label=f"sub-batch {batch_num}",
            )

            data = [
                [c["chunk_id"] for c in batch],
                [c["source_id"] for c in batch],
                [c["document_id"] for c in batch],
                [c["source_doc_url"] for c in batch],
                [c["section_ref"] for c in batch],
                [c["source_url"] for c in batch],   # ADDED
                [c["domain"] for c in batch],
                [c["subdomain"] for c in batch],
                [c["b2b_b2c"] for c in batch],
                [c["tier"] for c in batch],
                [c["jurisdiction"] for c in batch],
                [c["text"] for c in batch],
                [c["embedding"] for c in batch],
            ]

            payload_mb = sys.getsizeof(data) / (1024 * 1024)
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            logger.info(
                f"Batch {batch_num}: {len(batch)} rows | "
                f"payload={payload_mb:.2f}MB | cpu={cpu}% | mem={mem}%"
            )

            start = time.time()
            try:
                result = self.collection.insert(data)
                elapsed = time.time() - start
                logger.info(f"Batch {batch_num}: inserted in {elapsed:.2f}s")
                total_inserted += len(batch)
                all_pk.extend(result.primary_keys)
            except Exception as exc:
                elapsed = time.time() - start
                logger.error(
                    f"Batch {batch_num} INSERT FAILED after {elapsed:.2f}s: {exc}"
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