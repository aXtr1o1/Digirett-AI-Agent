import logging
from typing import List, Dict, Any, Set
from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility
)

logger = logging.getLogger(__name__)

class MilvusLovdataStore:
    def __init__(
        self,
        milvus_host: str,
        milvus_port: int,
        collection_name: str
    ):
        self.collection_name = collection_name
        self._processed_hashes: Set[str] = set()

        connections.connect(
            alias="default",
            host=milvus_host,
            port=milvus_port
        )

        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self) -> Collection:
        if utility.has_collection(self.collection_name):
            col = Collection(self.collection_name)
            col.load()
            return col

        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="file_name", dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="file_hash", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="chunk_index", dtype=DataType.INT64),
            FieldSchema(name="parent_index", dtype=DataType.INT64),
            FieldSchema(name="child_index", dtype=DataType.INT64),
            FieldSchema(name="parent_type", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="parent_title", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
        ]

        schema = CollectionSchema(fields, "Lovdata hierarchical chunks")
        col = Collection(self.collection_name, schema)

        col.create_index(
            field_name="embedding",
            index_params={
                "index_type": "HNSW",
                "metric_type": "IP",
                "params": {"M": 16, "efConstruction": 200}
            }
        )
        col.load()
        return col

    def insert_chunks(self, chunks: List[Dict[str, Any]]):
        file_hash = chunks[0]["file_hash"]

        if file_hash in self._processed_hashes:
            return {"skipped": True}

        data = [
            [c["stable_chunk_id"] for c in chunks],
            [c["file_name"] for c in chunks],
            [c["file_hash"] for c in chunks],
            [c["chunk_index"] for c in chunks],
            [c["parent_index"] for c in chunks],
            [c["child_index"] for c in chunks],
            [c["parent_type"] for c in chunks],
            [c["parent_title"] for c in chunks],
            [c["text"] for c in chunks],
            [c["embedding"] for c in chunks],
        ]

        result = self.collection.insert(data)
        self.collection.flush()

        self._processed_hashes.add(file_hash)

        return {
            "inserted": len(chunks),
            "milvus_ids": result.primary_keys
        }

    def close(self):
        connections.disconnect("default")