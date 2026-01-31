import logging
from typing import List, Dict, Any, Set

from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)

logger = logging.getLogger(__name__)


class MilvusTextStore:
    def __init__(
        self,
        milvus_host: str,
        milvus_port: int,
        collection_name: str,
        embedding_dim: int = 1024,
    ):
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self._processed_hashes: Set[str] = set()

        connections.connect(
            alias="default",
            host=milvus_host,
            port=milvus_port,
        )

        self.collection = self._get_or_create_collection()

    # --------------------------------------------------
    # IMPROVED EMBEDDING NORMALIZATION
    # --------------------------------------------------
    def _fix_embedding(self, emb):
        """
        Make embedding a flat List[float] for Milvus.
        Handles nested lists, dicts, numpy arrays, and various formats.
        """
        # unwrap dicts
        if isinstance(emb, dict):
            emb = emb.get("dense_vecs") or emb.get("embedding") or emb.get("vector")
            if emb is None:
                raise ValueError(f"Could not extract embedding from dict: {list(emb.keys())}")

        # numpy → list
        if hasattr(emb, "tolist"):
            emb = emb.tolist()

        # unwrap nested lists recursively
        while isinstance(emb, list) and len(emb) > 0 and isinstance(emb[0], list):
            logger.debug(f"Unwrapping nested list: shape={len(emb)}x{len(emb[0]) if emb else 0}")
            emb = emb[0]

        # Final validation and conversion
        if not isinstance(emb, list):
            raise TypeError(f"Embedding must be a list, got {type(emb)}")
        
        if len(emb) == 0:
            raise ValueError("Embedding is empty")
        
        # Check if elements are already numbers or need conversion
        if isinstance(emb[0], (int, float)):
            # Already flat numbers
            result = [float(x) for x in emb]
        elif isinstance(emb[0], list):
            # Still nested! This shouldn't happen but handle it
            raise ValueError(f"Embedding still nested after unwrapping: shape={len(emb)}x{len(emb[0])}")
        else:
            # Try to convert whatever it is
            try:
                result = [float(x) for x in emb]
            except (TypeError, ValueError) as e:
                raise TypeError(f"Cannot convert embedding elements to float: {type(emb[0])}, error: {e}")
        
        # Validate dimension
        if len(result) != self.embedding_dim:
            logger.warning(f"Embedding dimension mismatch: expected {self.embedding_dim}, got {len(result)}")
        
        return result

    # --------------------------------------------------
    # COLLECTION (✅ FIXED - Now creates collection)
    # --------------------------------------------------
    def _get_or_create_collection(self) -> Collection:
        """
        Load existing collection or create new one with correct schema (NO YEAR).
        
        Schema (12 fields total):
        1. id (auto-generated primary key)
        2. chunk_id
        3. file_name
        4. file_hash
        5. url
        6. chunk_index
        7. parent_index
        8. child_index
        9. parent_type
        10. parent_title
        11. text
        12. embedding
        """
        if utility.has_collection(self.collection_name):
            logger.info(f"✅ Loading existing Milvus collection: {self.collection_name}")
            col = Collection(self.collection_name)
            col.load()
            return col

        # ✅ CREATE NEW COLLECTION (instead of raising error)
        logger.info(f"🔨 Creating new Milvus collection: {self.collection_name}")
        
        # Define schema WITHOUT year field
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="file_name", dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="file_hash", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="chunk_index", dtype=DataType.INT64),
            FieldSchema(name="parent_index", dtype=DataType.INT64),
            FieldSchema(name="child_index", dtype=DataType.INT64),
            FieldSchema(name="parent_type", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="parent_title", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
        ]
        
        schema = CollectionSchema(
            fields=fields,
            description="Lovdata Norwegian Legal Documents - BGE-M3 (No Year Field)"
        )
        
        # Create collection
        collection = Collection(name=self.collection_name, schema=schema)
        
        # Create HNSW index for fast similarity search
        logger.info(f"🔍 Creating HNSW index on embedding field...")
        index_params = {
            "index_type": "HNSW",
            "metric_type": "IP",  # Inner Product for BGE-M3
            "params": {
                "M": 16,
                "efConstruction": 200
            }
        }
        
        collection.create_index(
            field_name="embedding",
            index_params=index_params
        )
        
        # Load collection into memory
        collection.load()
        
        logger.info(f"✅ Collection created and loaded successfully")
        logger.info(f"   Schema: {len(fields)} fields (including auto-id)")
        logger.info(f"   Index: HNSW with M=16, efConstruction=200")
        logger.info(f"   Metric: IP (Inner Product)")
        
        return collection

    # --------------------------------------------------
    # INSERT
    # --------------------------------------------------
    def insert_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Insert chunks into Milvus WITHOUT year field.
        
        Schema order (excluding auto-generated 'id'):
        1. chunk_id
        2. file_name
        3. file_hash
        4. url
        5. chunk_index
        6. parent_index
        7. child_index
        8. parent_type
        9. parent_title
        10. text
        11. embedding
        """
        if not chunks:
            return {"inserted": 0}

        normalized = []
        for i, c in enumerate(chunks):
            try:
                fixed_embedding = self._fix_embedding(c["embedding"])
                
                normalized.append({
                    "chunk_id": c.get("chunk_id") or c.get("stable_chunk_id"),
                    "file_name": c["file_name"],
                    "file_hash": c["file_hash"],
                    "url": c.get("url", ""),
                    "chunk_index": c["chunk_index"],
                    "parent_index": c.get("parent_index", 0),
                    "child_index": c.get("child_index", 0),
                    "parent_type": c.get("section_type") or c.get("parent_type") or "document",
                    "parent_title": c.get("section_title") or c.get("parent_title") or "",
                    "text": c["text"],
                    "embedding": fixed_embedding,
                })
            except Exception as e:
                logger.error(f"Failed to normalize chunk {i} for {c.get('file_name')}: {e}")
                logger.error(f"Embedding type: {type(c['embedding'])}")
                if isinstance(c['embedding'], list):
                    logger.error(f"Embedding length: {len(c['embedding'])}")
                    if len(c['embedding']) > 0:
                        logger.error(f"First element type: {type(c['embedding'][0])}")
                        if isinstance(c['embedding'][0], list):
                            logger.error(f"First element length: {len(c['embedding'][0])}")
                raise

        file_hash = normalized[0]["file_hash"]

        if file_hash in self._processed_hashes:
            logger.info("Duplicate file detected, skipping insertion")
            return {"skipped": True}

        # ✅ Data arrays in EXACT schema order (excluding auto-generated 'id')
        # Schema order WITHOUT YEAR: id (auto), chunk_id, file_name, file_hash, url,
        #                           chunk_index, parent_index, child_index, parent_type,
        #                           parent_title, text, embedding
        data = [
            [c["chunk_id"] for c in normalized],       # Field 2
            [c["file_name"] for c in normalized],      # Field 3
            [c["file_hash"] for c in normalized],      # Field 4
            [c["url"] for c in normalized],            # Field 5
            [c["chunk_index"] for c in normalized],    # Field 6
            [c["parent_index"] for c in normalized],   # Field 7
            [c["child_index"] for c in normalized],    # Field 8
            [c["parent_type"] for c in normalized],    # Field 9
            [c["parent_title"] for c in normalized],   # Field 10
            [c["text"] for c in normalized],           # Field 11
            [c["embedding"] for c in normalized],      # Field 12
        ]

        logger.debug(f"Inserting {len(normalized)} chunks with {len(data)} field arrays")

        result = self.collection.insert(data)
        self.collection.flush()

        self._processed_hashes.add(file_hash)

        return {
            "inserted": len(normalized),
            "milvus_ids": result.primary_keys,
        }

    def close(self):
        connections.disconnect("default")