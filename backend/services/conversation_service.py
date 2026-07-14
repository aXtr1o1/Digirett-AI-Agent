import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import settings
from db.redis_client import RedisClient
from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


class ConversationService:
   

    def __init__(
        self,
        supabase_client: SupabaseClient,
        redis_client: RedisClient,
    ) -> None:
        self._supabase = supabase_client
        self._cache = redis_client
        logger.info("ConversationService initialized")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CREATE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def create_conversation(
        self,
        user_id: str,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        
        try:
            conversation = self._supabase.create_conversation(
                user_id=user_id,
                title=title,
            )
            conversation_id = conversation["conversation_id"]

            # Warm the cache immediately
            self._cache.set_conversation_meta(conversation_id, conversation)
            self._cache.add_conversation_to_user(user_id, conversation_id)

            logger.info(f" Created conversation {conversation_id} for user {user_id}")
            return conversation

        except Exception as exc:
            logger.error(f" create_conversation failed | {exc}", exc_info=True)
            raise

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # READ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:

        try:
            cached = self._cache.get_conversation_meta(conversation_id)

            if cached:
                logger.debug(f" Conversation cache hit: {conversation_id}")

                # 🔥 Update updated_at even if coming from cache
                now = datetime.utcnow().isoformat()

                def _touch():
                    try:
                        self._supabase.table("conversations").update({
                            "updated_at": now
                        }).eq("conversation_id", conversation_id).execute()
                    except Exception:
                        pass
                
                import threading
                threading.Thread(target=_touch, daemon=True).start()

                cached["updated_at"] = now
                self._cache.set_conversation_meta(conversation_id, cached)

                return cached

            response = (
                self._supabase.table("conversations")
                .select("*")
                .eq("conversation_id", conversation_id)
                .eq("is_deleted", False)
                .execute()
            )

            if not response.data:
                logger.warning(f"⚠️  Conversation not found: {conversation_id}")
                return None

            conversation = response.data[0]

            # 🔥 Update updated_at when accessed
            now = datetime.utcnow().isoformat()

            def _touch2():
                try:
                    self._supabase.table("conversations").update({
                        "updated_at": now
                    }).eq("conversation_id", conversation_id).execute()
                except Exception:
                    pass
            
            import threading
            threading.Thread(target=_touch2, daemon=True).start()

            conversation["updated_at"] = now

            self._cache.set_conversation_meta(conversation_id, conversation)

            return conversation

        except Exception as exc:
            logger.error(f" get_conversation failed | {exc}")
            return None


    def get_user_conversations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:

        try:
            response = (
                self._supabase.table("conversations")
                .select("*")
                .eq("user_id", user_id)
                .or_("is_deleted.eq.false,is_deleted.is.null")
                .order("updated_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )

            conversations = response.data or []

            ids = [c["conversation_id"] for c in conversations]
            self._cache.set_user_conversations(user_id, ids)

            def _warm_cache():
                for conv in conversations:
                    try:
                        self._cache.set_conversation_meta(conv["conversation_id"], conv)
                    except Exception:
                        pass
            
            import threading
            threading.Thread(target=_warm_cache, daemon=True).start()

            logger.info(f" Loaded {len(conversations)} conversations for user {user_id}")
            return conversations

        except Exception as exc:
            logger.error(f" get_user_conversations failed | {exc}")
            return []

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # UPDATE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def update_title(self, conversation_id: str, title: str) -> bool:
        
        try:
            capped_title = title[:settings.MAX_CONVERSATION_TITLE_LENGTH]
            success = self._supabase.update_conversation_title(
                conversation_id=conversation_id,
                title=capped_title,
            )
            if success:
                # Invalidate stale cache; next read will repopulate from Supabase
                self._cache.clear_all_conversation_cache(conversation_id)
                logger.info(f" Updated title for {conversation_id}: '{capped_title}'")
            return success

        except Exception as exc:
            logger.error(f" update_title failed | {exc}")
            return False

    def update_summary(self, conversation_id: str, summary: str) -> bool:
        """Save a rolling summary of messages into the conversations table."""
        try:
            success = self._supabase.update_conversation_summary(
                conversation_id=conversation_id,
                summary=summary,
            )
            if success:
                # Invalidate cache so next read picks up the new summary
                cached = self._cache.get_conversation_meta(conversation_id)
                if cached:
                    cached["conversation_summary"] = summary
                    self._cache.set_conversation_meta(conversation_id, cached)
                logger.info(f"[OK] Summary updated for {conversation_id}")
            return success
        except Exception as exc:
            logger.error(f"[ERROR] update_summary failed | {exc}")
            return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DELETE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def delete_conversation(
        self,
        conversation_id: str,
        soft_delete: bool = True,
    ) -> bool:
        
        try:
            if soft_delete:
                success = self._supabase.soft_delete_conversation(conversation_id)
            else:
                self._supabase.table("conversations").delete().eq(
                    "conversation_id", conversation_id
                ).execute()
                success = True

            if success:
                self._cache.clear_all_conversation_cache(conversation_id)
                logger.info(f" Deleted conversation {conversation_id} | soft={soft_delete}")

            return success

        except Exception as exc:
            logger.error(f" delete_conversation failed | {exc}")
            return False