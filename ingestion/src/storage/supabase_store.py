import os
import hashlib
from supabase import create_client, Client
from datetime import datetime, timezone

from ingestion.src.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_KEY,
    SUPABASE_BUCKET,
    logger
)

class SupabaseStore:
    def __init__(self):
        self.supabase: Client = create_client(
            SUPABASE_URL,
            SUPABASE_SERVICE_KEY
        )

    # --------------------------------------------------
    # Hash Utility
    # --------------------------------------------------
    def calculate_hash(self, file_path: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    # --------------------------------------------------
    # Storage Upload (NO EXTENSION)
    # --------------------------------------------------
    def upload_xml_to_storage(self, file_path: str, clean_name: str) -> str:
            """
            Upload XML content WITHOUT extension.
            Returns PUBLIC storage URI.
            """
            with open(file_path, "rb") as f:
                self.supabase.storage.from_(SUPABASE_BUCKET).upload(
                    path=f"raw/{clean_name}",
                    file=f,
                    file_options={
                        "cache-control": "3600",
                        "upsert": "true",
                        "content-type": "application/xml"
                    }
                )

            base_url = SUPABASE_URL.rstrip("/")
            return (
                f"{base_url}/storage/v1/object/public/"
                f"{SUPABASE_BUCKET}/raw/{clean_name}"
            )


    # --------------------------------------------------
    # Legacy Method (KEEP – DO NOT REMOVE)
    # --------------------------------------------------
    def upload_xml_and_log(self, file_path: str, zip_name: str, file_hash: str = None):
        """
        Upload XML and insert FILE-LEVEL metadata ONLY.
        ❌ No stable_chunk_id
        ❌ No chunk_index
        ❌ No milvus_id
        """
        base_name = os.path.basename(file_path)
        clean_name = os.path.splitext(base_name)[0]

        if not file_hash:
            file_hash = self.calculate_hash(file_path)

        try:
            # Upload XML (no extension)
            with open(file_path, "rb") as f:
                self.supabase.storage.from_(SUPABASE_BUCKET).upload(
                    path=f"raw/{clean_name}",
                    file=f,
                    file_options={
                        "upsert": "true",
                        "content-type": "application/xml"
                    }
                )

            base_url = SUPABASE_URL.rstrip("/")
            storage_uri = (
                f"{base_url}/storage/v1/object/public/"
                f"{SUPABASE_BUCKET}/raw/{clean_name}"
            )

            metadata = {
                "zip_name": zip_name,
                "file_name": clean_name,
                "file_hash": file_hash,
                "file_size": os.path.getsize(file_path),
                "file_storage_uri": storage_uri,
                "milvus_inserted_at": datetime.now(timezone.utc).isoformat()
            }

            self.supabase.table("lovdata_metadata").insert(metadata).execute()
            logger.info(f"✅ Stored XML + metadata for {clean_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Supabase upload failed for {clean_name}: {e}")
            return False

    # --------------------------------------------------
    # ✅ NEW METHOD (FIXES YOUR ERROR)
    # --------------------------------------------------
    def insert_file_metadata(
        self,
        zip_name: str,
        file_name: str,
        file_hash: str,
        file_size: int,
        file_storage_uri: str
    ):
        """
        Insert ONE row per file.
        Matches Supabase table exactly.
        """
        try:
            metadata = {
                "zip_name": zip_name,
                "file_name": file_name,
                "file_hash": file_hash,
                "file_size": file_size,
                "file_storage_uri": file_storage_uri,
                "milvus_inserted_at": datetime.now(timezone.utc).isoformat()
            }

            self.supabase.table("lovdata_metadata").insert(metadata).execute()
            logger.info(f"✅ Metadata inserted for {file_name}")

        except Exception as e:
            logger.error(f"❌ Metadata insert failed for {file_name}: {e}")
            raise