from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from supabase import Client, create_client

from ingestion.src.config import (
    SUPABASE_BUCKET,
    SUPABASE_SERVICE_KEY,
    SUPABASE_SOURCE_TABLE_AI,
    SUPABASE_SOURCE_TABLE_PREDEFINED,
    SUPABASE_TABLE,
    SUPABASE_URL,
    SUPABASE_RAW_METADATA_TABLE,
)


logger = logging.getLogger(__name__)


class SupabaseStore:
    def __init__(self) -> None:
        self.supabase: Optional[Client] = None
        self._connected = False

    def _ensure_connection(self) -> None:
        if not self._connected:
            self.supabase = create_client(
                SUPABASE_URL,
                SUPABASE_SERVICE_KEY,
            )
            self._connected = True

    def _find_in_table_by_file_name(
        self,
        table_name: str,
        file_name: str,
    ) -> dict | None:
        self._ensure_connection()

        try:
            response = (
                self.supabase.table(table_name)
                .select("*")
                .eq("file_name", file_name)
                .limit(1)
                .execute()
            )

            if response.data:
                return response.data[0]

            return None

        except Exception as exc:
            logger.error(
                "find in table failed | table=%s | file=%s | error=%s",
                table_name,
                file_name,
                exc,
            )
            return None

    def find_source_metadata_by_file_name(
        self,
        file_name: str,
    ) -> dict | None:
        row = self._find_in_table_by_file_name(
            SUPABASE_SOURCE_TABLE_PREDEFINED,
            file_name,
        )

        if row:
            row["_matched_table"] = SUPABASE_SOURCE_TABLE_PREDEFINED
            return row

        row = self._find_in_table_by_file_name(
            SUPABASE_SOURCE_TABLE_AI,
            file_name,
        )

        if row:
            row["_matched_table"] = SUPABASE_SOURCE_TABLE_AI
            return row

        return None

    def download_xml_text_from_storage(
        self,
        bucket_path: str,
    ) -> str | None:
        self._ensure_connection()

        try:
            response = (
                self.supabase.storage
                .from_(SUPABASE_BUCKET)
                .download(bucket_path)
            )

            if response is None:
                return None

            if isinstance(response, bytes):
                return response.decode("utf-8")

            if hasattr(response, "decode"):
                return response.decode("utf-8")

            return str(response)

        except Exception as exc:
            logger.error(
                "download_xml_text_from_storage failed | path=%s | error=%s",
                bucket_path,
                exc,
            )
            return None

    def upsert_file_metadata(
        self,
        file_name: str,
        source_id: str,
        source_doc_url: str,
        domain: str,
        subdomain: str,
        b2b_b2c: str,
        tier: str,
        jurisdiction: str,
        legal_validation: str,
        xml_bucket_path: str,
        doc_title: str,
    ) -> bool:
        self._ensure_connection()

        now = datetime.now(timezone.utc).isoformat()

        row = {
            "file_name": file_name,
            "source_id": source_id,
            "source_doc_url": source_doc_url,
            "domain": domain,
            "subdomain": subdomain,
            "b2b_b2c": b2b_b2c,
            "tier": tier,
            "jurisdiction": jurisdiction,
            "legal_validation": legal_validation,
            "xml_bucket_path": xml_bucket_path,
            "doc_title": doc_title,
            "updated_at": now,
        }

        try:
            (
                self.supabase.table(SUPABASE_TABLE)
                .upsert(row, on_conflict="file_name")
                .execute()
            )

            logger.info(
                "Supabase file metadata upserted | file_name=%s | source_id=%s",
                file_name,
                source_id,
            )

            return True

        except Exception as exc:
            logger.error(
                "upsert_file_metadata failed | file_name=%s | error=%s",
                file_name,
                exc,
            )

            return False

    def upload_raw_content(
        self,
        content: bytes,
        file_name: str,
        bucket: str = None,
    ) -> str | None:
        """Uploads raw content to Supabase Storage and returns the path."""
        self._ensure_connection()
        target_bucket = bucket or SUPABASE_BUCKET

        try:
            # We use the file_name as the path in the bucket
            response = self.supabase.storage.from_(target_bucket).upload(
                path=file_name,
                file=content,
                file_options={"upsert": "true"}
            )
            # Supabase return might vary depending on version, usually it's a dict with 'path'
            if isinstance(response, dict):
                return response.get("path")
            return file_name # Fallback to file_name as path
        except Exception as exc:
            logger.error("upload_raw_content failed | file=%s | error=%s", file_name, exc)
            return None

    def upsert_raw_metadata(
        self,
        metadata: dict,
    ) -> bool:
        """Upserts metadata into the raw ingestion tracking table."""
        self._ensure_connection()
        now = datetime.now(timezone.utc).isoformat()
        
        metadata["updated_at"] = now
        if "created_at" not in metadata:
            metadata["created_at"] = now

        try:
            (
                self.supabase.table(SUPABASE_RAW_METADATA_TABLE)
                .upsert(metadata, on_conflict="file_name")
                .execute()
            )
            logger.info("Raw metadata upserted | file_name=%s", metadata.get("file_name"))
            return True
        except Exception as exc:
            logger.error("upsert_raw_metadata failed | file_name=%s | error=%s", metadata.get("file_name"), exc)
            return False