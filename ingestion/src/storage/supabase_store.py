import os
import hashlib
from supabase import create_client, Client
from datetime import datetime, timezone

from ingestion.src.config import (
    SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_BUCKET, logger
)

class SupabaseStore:
    def __init__(self):
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    def calculate_hash(self, file_path: str) -> str:
        """Calculates SHA256 hash for file integrity."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def upload_xml_and_log(self, file_path: str, zip_name: str, file_hash: str = None):
        base_name = os.path.basename(file_path)
        name_only = os.path.splitext(base_name)[0]
        
        if not file_hash:
            file_hash = self.calculate_hash(file_path)
            
        storage_path = f"raw/{name_only}"

        try:
            # 1. Physical Upload
            with open(file_path, 'rb') as f:
                self.supabase.storage.from_(SUPABASE_BUCKET).upload(
                    path=storage_path,
                    file=f,
                    file_options={"upsert": "true", "content-type": "application/xml"}
                )
            
            # 2. Fix URI construction
            base_url = SUPABASE_URL.rstrip('/')
            storage_uri = f"{base_url}/storage/v1/object/public/{SUPABASE_BUCKET}/{storage_path}"

            # 3. Initial Metadata Row
            metadata = {
            "zip_name": zip_name,
            "file_name": name_only,
            "file_hash": file_hash,
            "file_size": os.path.getsize(file_path),
            "file_storage_uri": storage_uri,
            # This generates a precise UTC timestamp that Supabase will record correctly
            "milvus_inserted_at": datetime.now(timezone.utc).isoformat(), 
            "stable_chunk_id": "pending",
            "chunk_index": 0,
            "milvus_id": 0
        }

            self.supabase.table("lovdata_metadata").insert(metadata).execute()
            logger.info(f"✅ Stored XML and metadata for: {name_only}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed Supabase storage for {name_only}: {e}")
            return False