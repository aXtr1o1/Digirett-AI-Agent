import os
import hashlib
from supabase import create_client, Client
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

from ingestion.src.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_KEY,
    SUPABASE_BUCKET
)


class SupabaseStore:
    """
    Supabase storage handler WITHOUT year field.
    Uploads XML files and manages metadata in lovdata_metadata table.
    """
    
    def __init__(self):
        self.supabase: Client | None = None
        self._connected = False
        self._uploaded_hashes = set()
    
    def _ensure_connection(self):
        if not self._connected:
            self.supabase = create_client(
                SUPABASE_URL,
                SUPABASE_SERVICE_KEY
            )
            self._connected = True


    def calculate_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def upload_xml_to_storage(self, file_path: str, destination_filename: str) -> bool:
        self._ensure_connection()
        
        """
        Upload XML WITHOUT .xml extension, with duplicate prevention.
        
        Args:
            file_path: Path to local XML file
            destination_filename: Target filename (extension will be removed)
            
        Returns:
            True if successful or already exists, False on error
        """
        try:
            # Remove .xml extension
            clean_name = os.path.splitext(destination_filename)[0]
            while clean_name.lower().endswith('.xml'):
                clean_name = clean_name[:-4]
            
            storage_path = f"raw/{clean_name}"
            
            # Check if exists
            try:
                existing = self.supabase.storage.from_(SUPABASE_BUCKET).list("raw")
                existing_files = {f['name'] for f in existing}
                
                if clean_name in existing_files:
                    logger.info(f"⏭️  File already exists in storage: {clean_name}, skipping upload")
                    return True
                    
            except Exception as check_error:
                logger.debug(f"Could not check existing files: {check_error}")
            
            # Upload
            with open(file_path, "rb") as f:
                self.supabase.storage.from_(SUPABASE_BUCKET).upload(
                    path=storage_path,
                    file=f,
                    file_options={
                        "cache-control": "3600",
                        "upsert": "false",
                        "content-type": "application/xml"
                    }
                )
            
            logger.info(f"✅ Uploaded to storage: {storage_path}")
            return True
            
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                logger.info(f"⏭️  File already exists: {clean_name}, skipping")
                return True
            
            logger.error(f"❌ Storage upload failed for {destination_filename}: {e}")
            return False

    def insert_file_metadata(
        self,
        file_name: str,
        file_hash: str,
        file_size: int,
        zip_name: str,
        url: str = None,
        file_storage_uri: str = None
    ):
        self._ensure_connection()

        """
        Insert file metadata WITHOUT year column.
        
        Args:
            file_name: Clean filename without extension
            file_hash: SHA256 hash of file
            file_size: File size in bytes
            zip_name: Source archive name
            url: Public URL (alias for file_storage_uri)
            file_storage_uri: Public storage URI
            
        Returns:
            True if successful or already exists
        """
        try:
            # Check if already processed in this session
            if file_hash in self._uploaded_hashes:
                logger.info(f"⏭️  File already processed in this session: {file_name}")
                return True
            
            # Check database for duplicates
            existing = self.supabase.table("lovdata_metadata")\
                .select("file_hash")\
                .eq("file_hash", file_hash)\
                .limit(1)\
                .execute()

            if existing.data:
                logger.info(f"⏭️  File already in database by name: {file_name}")
                self._uploaded_hashes.add(file_hash)
                return True
            
            # Build storage URI
            storage_uri = url or file_storage_uri
            if not storage_uri:
                raise ValueError("Either 'url' or 'file_storage_uri' must be provided")
            
            # Metadata WITHOUT year field
            metadata = {
                "zip_name": zip_name,
                "file_name": file_name,
                "file_hash": file_hash,
                "file_size": file_size,
                "file_storage_uri": storage_uri,
                "milvus_inserted_at": datetime.now(timezone.utc).isoformat()
            }

            self.supabase.table("lovdata_metadata").insert(metadata).execute()
            self._uploaded_hashes.add(file_hash)
            
            logger.info(f"✅ Metadata inserted for {file_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Metadata insert failed for {file_name}: {e}")
            raise

    def file_name_exists(self, file_name: str) -> bool:
        """Check if file with given NAME exists in database."""
        self._ensure_connection()
        try:
            response = (
                self.supabase
                .table("lovdata_metadata")
                .select("file_name")
                .eq("file_name", file_name)
                .limit(1)
                .execute()
            )
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"❌ Error checking file name existence: {e}")
            return False

    # ✅ ADD THIS METHOD RIGHT HERE
    def file_exists(self, file_hash: str) -> bool:
        """Check if file with given HASH exists in database (for test compatibility)."""
        self._ensure_connection()
        try:
            response = (
                self.supabase
                .table("lovdata_metadata")
                .select("file_hash")
                .eq("file_hash", file_hash)
                .limit(1)
                .execute()
            )
            return len(response.data) > 0
        except Exception:
            return False
        
    def zip_already_processed(self, zip_name: str) -> bool:
        """
        Check whether a ZIP archive has already been ingested.
        """
        self._ensure_connection()

        try:
            response = (
                self.supabase
                .table("lovdata_metadata")
                .select("zip_name")
                .eq("zip_name", zip_name)
                .limit(1)
                .execute()
            )

            return len(response.data) > 0

        except Exception as e:
            logger.error(f"❌ ZIP check failed: {e}")
            return False
        
    def classify_file(self, file_name: str, file_hash: str) -> str:
        """
        Classify file as NEW, UPDATED, or UNCHANGED.

        Rules:
        - File name not found          -> NEW
        - File name exists, hash same  -> UNCHANGED
        - File name exists, hash diff  -> UPDATED
        """
        self._ensure_connection()

        try:
            response = (
                self.supabase
                .table("lovdata_metadata")
                .select("file_hash")
                .eq("file_name", file_name)
                .limit(1)
                .execute()
            )

            # No record → NEW FILE
            if not response.data:
                return "NEW"

            existing_hash = response.data[0]["file_hash"]

            # Same content
            if existing_hash == file_hash:
                return "UNCHANGED"

            # Same name, different content
            return "UPDATED"

        except Exception as e:
            logger.error(f"❌ Classification failed for {file_name}: {e}")
            raise
    
    def get_all_file_hashes(self) -> set:
        """Retrieve all file hashes from database."""
        self._ensure_connection()
        try:
            response = self.supabase.table("lovdata_metadata").select("file_hash").execute()
            return {row['file_hash'] for row in response.data if row.get('file_hash')}
        except Exception as e:
            logger.error(f"❌ Error fetching file hashes: {e}")
            return set()
        
    def get_all_file_names(self) -> set:
        """Retrieve ALL file names from database using pagination."""
        self._ensure_connection()

        try:
            all_files = set()
            batch_size = 1000
            offset = 0

            while True:
                response = (
                    self.supabase
                    .table("lovdata_metadata")
                    .select("file_name")
                    .range(offset, offset + batch_size - 1)
                    .execute()
                )

                data = response.data

                if not data:
                    break

                for row in data:
                    if row.get("file_name"):
                        all_files.add(row["file_name"])

                offset += batch_size
                logger.info(f"Fetched {len(all_files)} Supabase file names...")

            return all_files

        except Exception as e:
            logger.error(f"❌ Error fetching file names: {e}")
            return set()

    # ✅ ADD THIS METHOD HERE
    def delete_xml_from_storage(self, file_name: str):
        """
        Delete XML file from Supabase storage (rollback use).
        """
        self._ensure_connection()

        try:
            clean_name = os.path.splitext(file_name)[0]
            storage_path = f"raw/{clean_name}"

            self.supabase.storage.from_(SUPABASE_BUCKET).remove([storage_path])

            logger.warning(f"🧹 Rolled back storage file: {storage_path}")

        except Exception as e:
            logger.error(f"❌ Failed to delete storage file {file_name}: {e}")
        
    def cleanup_duplicate_xml_files(self):
        """Remove .xml files from storage (cleanup utility)."""
        self._ensure_connection()
        try:
            logger.info("🧹 Cleaning up duplicate .xml files...")
            files = self.supabase.storage.from_(SUPABASE_BUCKET).list("raw")
            xml_files = [f['name'] for f in files if f['name'].endswith('.xml')]
            
            if not xml_files:
                logger.info("✅ No .xml files to clean up")
                return
            
            logger.info(f"Found {len(xml_files)} .xml files to remove")
            
            batch_size = 50
            for i in range(0, len(xml_files), batch_size):
                batch = xml_files[i:i+batch_size]
                paths = [f"raw/{name}" for name in batch]
                self.supabase.storage.from_(SUPABASE_BUCKET).remove(paths)
                logger.info(f"🗑️  Deleted {len(batch)} .xml files")
            
            logger.info(f"✅ Cleanup complete: removed {len(xml_files)} files")
            
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")