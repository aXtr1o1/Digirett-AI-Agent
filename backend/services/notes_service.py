import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

class NotesService:
    def __init__(self, supabase_client):
        self._supabase = supabase_client

    def get_notes_by_lawyer(self, lawyer_id: str) -> List[Dict[str, Any]]:
        """Fetch all notes for a specific lawyer, ordered by updated_at descending."""
        try:
            resp = self._supabase.table("lawyer_notes") \
                .select("*") \
                .eq("lawyer_id", lawyer_id) \
                .order("updated_at", desc=True) \
                .execute()
            return resp.data or []
        except Exception as exc:
            logger.error(f"Failed to fetch notes for lawyer {lawyer_id}: {exc}")
            raise

    def create_note(self, lawyer_id: str, title: str, content: str) -> Optional[Dict[str, Any]]:
        """Create a new note for a lawyer."""
        try:
            data = {
                "lawyer_id": lawyer_id,
                "title": title,
                "content": content
            }
            resp = self._supabase.table("lawyer_notes").insert(data).execute()
            if resp.data:
                return resp.data[0]
            return None
        except Exception as exc:
            logger.error(f"Failed to create note for lawyer {lawyer_id}: {exc}")
            raise

    def update_note(self, note_id: str, lawyer_id: str, title: str, content: str) -> Optional[Dict[str, Any]]:
        """Update an existing note. Ensures the note belongs to the lawyer."""
        try:
            # We use an explicit eq for lawyer_id to ensure a lawyer can only update their own notes
            resp = self._supabase.table("lawyer_notes") \
                .update({"title": title, "content": content, "updated_at": "now()"}) \
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
