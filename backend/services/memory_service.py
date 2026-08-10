import logging
from typing import Any, Dict, List, Optional

from utils.context_builder import ContextBuilder

logger = logging.getLogger(__name__)

from config import settings

# Unified constant aligned with OrchestratorAgent
val = getattr(settings, "INTENT_CONTEXT_MESSAGES", 2)
INTENT_CONTEXT_MESSAGES = min(val, 6) if isinstance(val, int) else 2




class ConversationMemoryService:

    def __init__(self, redis_client: Any, supabase_client: Any) -> None:
        self._redis = redis_client
        self._supabase = supabase_client
        logger.info("[OK] ConversationMemoryService initialized")

    def run(self, conversation_id: str, limit: int = 10) -> List[Dict[str, str]]:
        logger.debug(f"ConversationMemoryService: loading history | conversation_id={conversation_id}")

        # ── Redis fast path ───────────────────────────────────────────────
        try:
            cached = self._redis.get_context(conversation_id)
            if cached:
                messages = self._normalize(cached[-limit:])
                logger.debug(f"ConversationMemoryService (Redis): {len(messages)} messages")
                return messages
        except Exception as exc:
            logger.warning(f" ConversationMemoryService Redis error: {exc}")

        # ── Supabase fallback ─────────────────────────────────────────────
        try:
            response = (
                self._supabase.table("messages")
                .select("role, content, created_at")
                .eq("conversation_id", conversation_id)
                .or_("is_deleted.is.null,is_deleted.eq.false")
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
            messages = self._normalize(response.data or [])
            logger.debug(f"ConversationMemoryService (Supabase): {len(messages)} messages")
            return messages
        except Exception as exc:
            logger.error(f" ConversationMemoryService Supabase error: {exc}", exc_info=True)
            return []

    def build_intent_context(
        self,
        conversation_id: str,
        current_query: str,
        n_messages: int = INTENT_CONTEXT_MESSAGES,
    ) -> str:
        history = self.run(conversation_id, limit=n_messages)
        if not history:
            return current_query

        return (
            ContextBuilder()
            .add_messages(history)
            .add_query(current_query)
            .build()
        )

    # ── Internal ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(raw: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Strip extra fields; keep only role + content."""
        result = []
        for msg in raw:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                result.append({"role": role, "content": content})
        return result


# Backward-compatible alias for existing imports
MemoryAgent = ConversationMemoryService
