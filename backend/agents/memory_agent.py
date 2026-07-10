import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryAgent:

    # Generate/refresh summary after every 2 messages
    SUMMARY_EVERY_N = 2

    def __init__(self, redis_client: Any, supabase_client: Any) -> None:
        self._redis = redis_client
        self._supabase = supabase_client
        logger.info("[OK] MemoryAgent initialized")

    def run(self, conversation_id: str, limit: int = 10) -> List[Dict[str, str]]:
        logger.debug(f"MemoryAgent: loading history | conversation_id={conversation_id}")

        # ── Redis fast path ───────────────────────────────────────────────
        try:
            cached = self._redis.get_context(conversation_id)
            if cached:
                messages = self._normalize(cached[-limit:])
                logger.debug(f"MemoryAgent (Redis): {len(messages)} messages")
                return messages
        except Exception as exc:
            logger.warning(f"[WARN] MemoryAgent Redis error: {exc}")

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
            logger.debug(f"MemoryAgent (Supabase): {len(messages)} messages")
            return messages
        except Exception as exc:
            logger.error(f"[ERROR] MemoryAgent Supabase error: {exc}", exc_info=True)
            return []

    def get_conversation_summary(self, conversation_id: str) -> Optional[str]:
        """
        Read conversation_summary from the conversations table.
        Returns None if no summary exists yet.
        """
        try:
            response = (
                self._supabase.table("conversations")
                .select("conversation_summary")
                .eq("conversation_id", conversation_id)
                .single()
                .execute()
            )
            if response.data:
                return response.data.get("conversation_summary")
            return None
        except Exception as exc:
            logger.warning(f"[WARN] MemoryAgent get_conversation_summary failed | {exc}")
            return None

    async def maybe_update_summary(
        self,
        conversation_id: str,
        llm_service: Any,
        conversation_service: Any,
    ) -> None:
        """
        Count messages for this conversation. If the count is a multiple of
        SUMMARY_EVERY_N (10, 20, 30 ...), generate a fresh summary from the
        last 10 messages and save it to conversations.conversation_summary.

        Call this AFTER saving a new user+assistant exchange (so count is up to date).
        """
        try:
            count_resp = (
                self._supabase.table("messages")
                .select("message_id", count="exact")
                .eq("conversation_id", conversation_id)
                .or_("is_deleted.is.null,is_deleted.eq.false")
                .execute()
            )
            total = count_resp.count or 0

            if total == 0 or total % self.SUMMARY_EVERY_N != 0:
                return  # not time yet

            logger.info(
                f"MemoryAgent: {total} messages — generating summary for {conversation_id}"
            )

            # Fetch the last 10 messages to summarise
            msgs_resp = (
                self._supabase.table("messages")
                .select("role, content")
                .eq("conversation_id", conversation_id)
                .or_("is_deleted.is.null,is_deleted.eq.false")
                .order("created_at", desc=True)
                .limit(self.SUMMARY_EVERY_N)
                .execute()
            )
            recent = list(reversed(msgs_resp.data or []))

            if not recent:
                return

            summary = await llm_service.generate_conversation_summary(recent)
            conversation_service.update_summary(conversation_id, summary)
            logger.info(f"[OK] MemoryAgent: summary saved for {conversation_id}")

        except Exception as exc:
            logger.warning(f"[WARN] MemoryAgent maybe_update_summary failed | {exc}")

    def build_intent_context(
        self,
        conversation_id: str,
        current_query: str,
        n_messages: int = 2,
    ) -> str:
        history = self.run(conversation_id, limit=n_messages)
        if not history:
            return current_query

        parts = [f"{m['role'].capitalize()}: {m['content']}" for m in history]
        parts.append(f"User: {current_query}")
        return "\n".join(parts)

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