"""
utils/storage_service.py — Storage Abstraction Wrapper for Supabase Storage
"""

import logging
from typing import Any, List, Optional, Union

logger = logging.getLogger(__name__)


class StorageService:
    """
    Lightweight wrapper exposing upload(), download(), and delete() operations
    over Supabase Storage buckets while preserving underlying client behavior.
    """

    def __init__(self, supabase_client: Any) -> None:
        self._supabase = supabase_client

    def _get_client(self) -> Any:
        client = self._supabase
        if hasattr(client, "_get"):
            client = client._get()
        return client

    def upload(
        self,
        bucket: str,
        path: str,
        file_bytes: bytes,
        content_type: str = "application/pdf",
        upsert: bool = False,
    ) -> bool:
        """Upload raw binary bytes to the specified storage bucket."""
        try:
            client = self._get_client()
            file_options = {"content-type": content_type}
            if upsert:
                file_options["upsert"] = "true"

            client.storage.from_(bucket).upload(
                path=path,
                file=file_bytes,
                file_options=file_options,
            )
            logger.info(f"💾 StorageService: Uploaded file | bucket={bucket} | path={path}")
            return True
        except Exception as exc:
            logger.error(f"❌ StorageService upload failed | bucket={bucket} | path={path} | {exc}", exc_info=True)
            raise

    def download(self, bucket: str, path: str) -> bytes:
        """Download binary file bytes from the specified storage bucket."""
        try:
            client = self._get_client()
            content = client.storage.from_(bucket).download(path)
            logger.info(f"📥 StorageService: Downloaded file | bucket={bucket} | path={path}")
            return content
        except Exception as exc:
            logger.error(f"❌ StorageService download failed | bucket={bucket} | path={path} | {exc}", exc_info=True)
            raise

    def delete(self, bucket: str, paths: Union[str, List[str]]) -> bool:
        """Delete single or multiple file paths from the specified storage bucket."""
        path_list = [paths] if isinstance(paths, str) else paths
        if not path_list:
            return True

        try:
            client = self._get_client()
            client.storage.from_(bucket).remove(path_list)
            logger.info(f"🗑️ StorageService: Deleted files | bucket={bucket} | count={len(path_list)}")
            return True
        except Exception as exc:
            logger.warning(f"⚠️ StorageService delete failed | bucket={bucket} | {exc}")
            return False
