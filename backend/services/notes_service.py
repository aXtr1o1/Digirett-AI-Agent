import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

from datetime import datetime, timezone

class NotesService:
    def __init__(self, supabase_client):
        self._supabase = supabase_client

    def get_notes_by_lawyer(
        self,
        lawyer_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fetch notes for a specific lawyer with optional limit/offset pagination."""
        try:
            query = self._supabase.table("lawyer_notes") \
                .select("*") \
                .eq("lawyer_id", lawyer_id) \
                .order("updated_at", desc=True)
            if limit:
                query = query.range(offset, offset + limit - 1)
            resp = query.execute()
            return resp.data or []
        except Exception as exc:
            logger.error(f"Failed to fetch notes for lawyer {lawyer_id}: {exc}")
            raise

    def create_note(self, lawyer_id: str, title: str, content: str) -> Optional[Dict[str, Any]]:
        """Create a new note for a lawyer."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            data = {
                "lawyer_id": lawyer_id,
                "title": title,
                "content": content,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            resp = self._supabase.table("lawyer_notes").insert(data).execute()
            if resp.data:
                return resp.data[0]
            return None
        except Exception as exc:
            logger.error(f"Failed to create note for lawyer {lawyer_id}: {exc}")
            raise

    def update_note(self, note_id: str, lawyer_id: str, title: str, content: str) -> Optional[Dict[str, Any]]:
        """Update an existing note with clean ISO timestamp. Ensures the note belongs to the lawyer."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            resp = self._supabase.table("lawyer_notes") \
                .update({"title": title, "content": content, "updated_at": now_iso}) \
                .eq("id", note_id) \
                .eq("lawyer_id", lawyer_id) \
                .execute()
            if resp.data:
                return resp.data[0]
            return None
        except Exception as exc:
            logger.error(f"Failed to update note {note_id}: {exc}")
            raise

    def delete_note(self, note_id: str, lawyer_id: str) -> bool:
        """Delete an existing note. Ensures the note belongs to the lawyer."""
        try:
            resp = self._supabase.table("lawyer_notes") \
                .delete() \
                .eq("id", note_id) \
                .eq("lawyer_id", lawyer_id) \
                .execute()
            return True
        except Exception as exc:
            logger.error(f"Failed to delete note {note_id}: {exc}")
            raise
