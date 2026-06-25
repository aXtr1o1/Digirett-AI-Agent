import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

class LibraryService:
    def __init__(self, supabase_client):
        self._supabase = supabase_client

    def save_message(self, user_id: str, message_id: str, note: Optional[str] = "") -> Optional[Dict[str, Any]]:
        """Save a message to the library, with conflict handling if already bookmarked."""
        try:
            data = {
                "user_id": user_id,
                "message_id": message_id,
                "note": note or ""
            }
            # Try to insert. Supabase doesn't have an upsert/on_conflict exposed in the same way,
            # but we can check if it exists or use upsert.
            # PostgREST upsert with on_conflict:
            resp = self._supabase.table("saved_messages").upsert(data, on_conflict="user_id,message_id").execute()
            if resp.data:
                return resp.data[0]
            return None
        except Exception as exc:
            logger.error(f"Failed to save message {message_id} to library for user {user_id}: {exc}")
            raise

    def get_saved_messages(self, user_id: str) -> List[Dict[str, Any]]:
        """Load saved message references joined with messages and conversation titles."""
        try:
            # Automatically clean up bookmarked messages older than 30 days
            from datetime import datetime, timedelta, timezone
            thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            try:
                self._supabase.table("saved_messages") \
                    .delete() \
                    .eq("user_id", user_id) \
                    .lt("saved_at", thirty_days_ago) \
                    .execute()
            except Exception as cleanup_exc:
                logger.warning(f"Failed to perform 30-day library cleanup for user {user_id}: {cleanup_exc}")

            # We select saved_messages and join messages and conversations to get all required data
            resp = self._supabase.table("saved_messages") \
                .select("*, messages(message_id, role, content, sources, metadata, created_at, conversation_id, conversations(title))") \
                .eq("user_id", user_id) \
                .order("saved_at", desc=True) \
                .execute()
            
            raw_list = resp.data or []
            normalized = []
            for item in raw_list:
                msg = item.get("messages")
                if not msg:
                    continue
                
                conv = msg.get("conversations")
                conv_title = conv.get("title") if conv else "Conversation"
                
                normalized.append({
                    "id": item.get("id"),
                    "message_id": item.get("message_id"),
                    "content": msg.get("content", ""),
                    "role": msg.get("role", "assistant"),
                    "conversation_id": msg.get("conversation_id"),
                    "conversation_title": conv_title,
                    "saved_at": item.get("saved_at"),
                    "sources": msg.get("sources") or [],
                    "metadata": msg.get("metadata") or {},
                    "note": item.get("note") or ""
                })
            return normalized
        except Exception as exc:
            logger.error(f"Failed to fetch saved messages for user {user_id}: {exc}")
            raise

    def delete_saved_message(self, message_id: str, user_id: str) -> bool:
        """Remove a message bookmark from library by message_id."""
        try:
            self._supabase.table("saved_messages") \
                .delete() \
                .eq("message_id", message_id) \
                .eq("user_id", user_id) \
                .execute()
            return True
        except Exception as exc:
            logger.error(f"Failed to delete saved message {message_id} for user {user_id}: {exc}")
            raise

    def update_saved_message_note(self, message_id: str, user_id: str, note: str) -> Optional[Dict[str, Any]]:
        """Update notes/annotations for a saved message."""
        try:
            resp = self._supabase.table("saved_messages") \
                .update({"note": note}) \
                .eq("message_id", message_id) \
                .eq("user_id", user_id) \
                .execute()
            if resp.data:
                return resp.data[0]
            return None
        except Exception as exc:
            logger.error(f"Failed to update note for message {message_id} (user {user_id}): {exc}")
            raise
