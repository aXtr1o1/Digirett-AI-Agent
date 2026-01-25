"""
Milvus Storage Module for Lovdata - Production Ready
Handles BGE-M3 (IP) and full Supabase metadata synchronization with De-duplication.
"""

import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility
)
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class MilvusLovdataStore:
    def __init__(
        self,
        milvus_host: str,
        milvus_port: int,
        collection_name: str,
        supabase_url: str,
        supabase_key: str
    ):
        self.milvus_host = milvus_host
        self.milvus_port = milvus_port
        self.collection_name = collection_name
        self.supabase = create_client(supabase_url, supabase_key)
        
        self._connect()
        self.collection = self._get_or_create_collection()

    def _connect(self):
        try:
            connections.connect(
                alias="default",
                host=self.milvus_host,
                port=self.milvus_port
            )
            logger.info(f"✅ Connected to Remote Milvus at {self.milvus_host}")
        except Exception as e:
            logger.error(f"❌ Milvus connection failed: {e}")
            raise

    def _get_or_create_collection(self) -> Collection:
        if utility.has_collection(self.collection_name):
            col = Collection(self.collection_name)
            col.load()
            return col

        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="stable_chunk_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="file_name", dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="file_hash", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="chunk_index", dtype=DataType.INT64),
            FieldSchema(name="parent_index", dtype=DataType.INT64),
            FieldSchema(name="child_index", dtype=DataType.INT64),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
        ]
        
        schema = CollectionSchema(fields, "Lovdata BGE-M3 Final Storage")
        collection = Collection(name=self.collection_name, schema=schema)

        index_params = {
            "index_type": "HNSW",
            "metric_type": "IP",
            "params": {"M": 16, "efConstruction": 200}
        }
        collection.create_index(field_name="embedding", index_params=index_params)
        collection.load()
        return collection

    def get_existing_hashes(self) -> Set[str]:
        """Retrieves all existing file_hash values from Supabase metadata."""
        try:
            response = self.supabase.table("lovdata_metadata").select("file_hash").execute()
            existing_hashes = {row['file_hash'] for row in response.data if row.get('file_hash')}
            logger.info(f"📊 Found {len(existing_hashes)} unique file hashes in database")
            return existing_hashes
        except Exception as e:
            logger.warning(f"⚠️ Could not retrieve existing hashes: {e}")
            return set()

    def hash_exists(self, file_hash: str) -> bool:
        """Checks if a specific file_hash already exists in Supabase."""
        try:
            response = self.supabase.table("lovdata_metadata").select("file_hash").eq("file_hash", file_hash).limit(1).execute()
            exists = len(response.data) > 0
            if exists:
                logger.info(f"🔍 Hash {file_hash[:12]}... already exists in database")
            return exists
        except Exception as e:
            logger.warning(f"⚠️ Hash existence check failed: {e}")
            return False

    def delete_by_hash(self, file_hash: str):
        """Deletes existing chunks with the same file_hash to avoid duplicates."""
        try:
            # First, delete from Supabase metadata
            self.supabase.table("lovdata_metadata").delete().eq("file_hash", file_hash).execute()
            
            # Then, delete from Milvus using an expression
            expr = f'file_hash == "{file_hash}"'
            res = self.collection.delete(expr)
            logger.info(f"🗑️ De-duplication: Removed existing records for hash {file_hash[:12]}... (Deleted: {res.delete_count})")
        except Exception as e:
            logger.warning(f"⚠️ De-duplication check skipped or failed: {e}")

    def insert_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Inserts vectors and syncs ALL metadata to Supabase in one batch."""
        if not chunks: return {"inserted": 0}
        
        # De-duplicate before inserting
        target_hash = chunks[0]['file_hash']
        self.delete_by_hash(target_hash)
        
        data = [
            [c['stable_chunk_id'] for c in chunks],
            [c['file_name'] for c in chunks],
            [c['file_hash'] for c in chunks],
            [c['chunk_index'] for c in chunks],
            [c['parent_index'] for c in chunks],
            [c['child_index'] for c in chunks],
            [c['embedding'] for c in chunks],
        ]
        
        res = self.collection.insert(data)
        self.collection.flush()
        
        # Capture generated IDs and sync to Supabase
        self._sync_to_supabase(chunks, res.primary_keys)
            
        return {"inserted": len(chunks), "milvus_ids": res.primary_keys}

    def _sync_to_supabase(self, chunks: List[Dict[str, Any]], milvus_ids: List[int]):
        """Populates all columns including file_size and zip_name."""
        records = []
        timestamp = datetime.utcnow().isoformat()
        
        for c, m_id in zip(chunks, milvus_ids):
            records.append({
                "stable_chunk_id": c["stable_chunk_id"],
                "chunk_index": c["chunk_index"],
                "milvus_id": m_id,
                "file_name": c["file_name"],
                "file_hash": c["file_hash"],
                "file_size": c.get("file_size"),
                "zip_name": c.get("zip_name"),
                "file_storage_uri": c.get("file_storage_uri"),
                "milvus_inserted_at": timestamp
            })
        
        self.supabase.table("lovdata_metadata").insert(records).execute()
        logger.info(f"🔗 Supabase sync successful: {len(records)} rows added.")

    def close(self):
        connections.disconnect("default")