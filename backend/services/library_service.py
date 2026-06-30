import logging
import uuid
import fitz  # PyMuPDF
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

class LibraryService:
    def __init__(self, supabase_client):
        self._supabase = supabase_client

    def _parse_text(self, file_bytes: bytes, file_type: str) -> str:
        """Helper to extract text from PDF or DOCX file bytes."""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf" if file_type == "pdf" else "docx")
            pages = []
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pages.append(page.get_text("text"))
            return "\n".join(pages)
        except Exception as exc:
            logger.warning(f"Failed to parse document content for text extraction: {exc}")
            return ""

    def save_document(
        self,
        user_id: str,
        file_name: str,
        file_type: str,
        file_bytes: bytes,
        note: Optional[str] = ""
    ) -> Optional[Dict[str, Any]]:
        """Save a new document to the library, uploading it to storage and recording metadata."""
        try:
            document_id = str(uuid.uuid4())
            extracted_text = self._parse_text(file_bytes, file_type)
            char_count = len(extracted_text)

            # Upload binary file to existing storage bucket
            storage_path = f"library/{document_id}.{file_type}"
            content_type = "application/pdf" if file_type == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            
            try:
                # Access the client storage
                client = self._supabase
                if hasattr(client, "_get"):
                    client = client._get()
                
                client.storage.from_("lovdata-documents").upload(
                    path=storage_path,
                    file=file_bytes,
                    file_options={"content-type": content_type}
                )
                logger.info(f"Binary file uploaded to library storage | path={storage_path}")
            except Exception as storage_exc:
                logger.error(f"Supabase Storage upload failed for library doc: {storage_exc}")
                raise

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(days=30)

            data = {
                "id": document_id,
                "user_id": user_id,
                "file_name": file_name,
                "file_type": file_type,
                "char_count": char_count,
                "extracted_text": extracted_text,
                "note": note or "",
                "storage_path": storage_path,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat()
            }

            resp = self._supabase.table("library_documents").insert(data).execute()
            if resp.data:
                return resp.data[0]
            return None
        except Exception as exc:
            logger.error(f"Failed to save document {file_name} to library for user {user_id}: {exc}")
            raise

    def get_library_documents(self, user_id: str) -> List[Dict[str, Any]]:
        """Load library documents for a user, cleaning up expired items first."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            
            # Automatically clean up library documents older than 30 days
            try:
                expired = self._supabase.table("library_documents") \
                    .select("id, storage_path") \
                    .eq("user_id", user_id) \
                    .lt("expires_at", now_iso) \
                    .execute()
                
                if expired.data:
                    client = self._supabase
                    if hasattr(client, "_get"):
                        client = client._get()
                    
                    for item in expired.data:
                        try:
                            client.storage.from_("lovdata-documents").remove([item["storage_path"]])
                        except Exception as storage_del_exc:
                            logger.warning(f"Failed to delete expired file {item['storage_path']} from storage: {storage_del_exc}")
                    
                    self._supabase.table("library_documents") \
                        .delete() \
                        .eq("user_id", user_id) \
                        .lt("expires_at", now_iso) \
                        .execute()
            except Exception as cleanup_exc:
                logger.warning(f"Failed to perform 30-day library documents cleanup for user {user_id}: {cleanup_exc}")

            resp = self._supabase.table("library_documents") \
                .select("*") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .execute()
            
            return resp.data or []
        except Exception as exc:
            logger.error(f"Failed to fetch library documents for user {user_id}: {exc}")
            raise

    def delete_library_document(self, document_id: str, user_id: str) -> bool:
        """Remove a document from the library and delete its storage file."""
        try:
            # 1. Fetch metadata to get the storage path
            doc_data = self._supabase.table("library_documents") \
                .select("storage_path") \
                .eq("id", document_id) \
                .eq("user_id", user_id) \
                .single() \
                .execute()
            
            if doc_data.data:
                storage_path = doc_data.data["storage_path"]
                # Delete from Storage
                try:
                    client = self._supabase
                    if hasattr(client, "_get"):
                        client = client._get()
                    client.storage.from_("lovdata-documents").remove([storage_path])
                except Exception as storage_del_exc:
                    logger.warning(f"Failed to remove library document {storage_path} from storage: {storage_del_exc}")

            # 2. Delete from DB
            self._supabase.table("library_documents") \
                .delete() \
                .eq("id", document_id) \
                .eq("user_id", user_id) \
                .execute()
            return True
        except Exception as exc:
            logger.error(f"Failed to delete library document {document_id} for user {user_id}: {exc}")
            raise

    def update_library_document_note(self, document_id: str, user_id: str, note: str) -> Optional[Dict[str, Any]]:
        """Update notes/annotations for a library document."""
        try:
            resp = self._supabase.table("library_documents") \
                .update({"note": note}) \
                .eq("id", document_id) \
                .eq("user_id", user_id) \
                .execute()
            if resp.data:
                return resp.data[0]
            return None
        except Exception as exc:
            logger.error(f"Failed to update note for library document {document_id} (user {user_id}): {exc}")
            raise
