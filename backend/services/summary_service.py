"""
services/summary_service.py — Conversation Summary Service

Responsible for summary generation, validation, and database persistence.
Separated from memory retrieval per Single Responsibility Principle (SRP).
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── CONSTANTS ────────────────────────────────────────────────────────
SUMMARY_EVERY_N = 2
MAX_SUMMARY_LENGTH = 2000


class SummaryService:

    def __init__(self, supabase_client: Any) -> None:
        self._supabase = supabase_client
        logger.info("[OK] SummaryService initialized")

    def get_conversation_summary(self, conversation_id: str) -> Optional[str]:
        """Read conversation_summary from the conversations table."""
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
            logger.warning(f"⚠️ SummaryService get_conversation_summary failed | {exc}")
            return None

    def validate_and_format_summary(self, raw_summary: Optional[str]) -> Optional[str]:
        """Enforces non-empty check, whitespace stripping, and max length bounds."""
        if not raw_summary or not isinstance(raw_summary, str):
            return None
        cleaned = raw_summary.strip()
        if not cleaned:
            return None
        if len(cleaned) > MAX_SUMMARY_LENGTH:
            logger.warning(f"⚠️ Summary length ({len(cleaned)}) exceeds {MAX_SUMMARY_LENGTH} limit. Truncating.")
            cleaned = cleaned[:MAX_SUMMARY_LENGTH] + "..."
        return cleaned

    async def maybe_update_summary(
        self,
        conversation_id: str,
        llm_service: Any,
        conversation_service: Any,
    ) -> None:
        """
        Count messages for this conversation. If count is a multiple of SUMMARY_EVERY_N,
        generate a summary, validate it, and persist it.
        """
        try:
            msgs_resp = (
                self._supabase.table("messages")
                .select("role, content")
                .eq("conversation_id", conversation_id)
                .or_("is_deleted.is.null,is_deleted.eq.false")
                .order("created_at", desc=True)
                .limit(SUMMARY_EVERY_N * 5)
                .execute()
            )
            recent = list(reversed(msgs_resp.data or []))
            total_messages = len(recent)

            if total_messages == 0 or total_messages % SUMMARY_EVERY_N != 0:
                return

            logger.info(f"SummaryService: generating summary for conversation {conversation_id}")
            raw_summary = await llm_service.generate_conversation_summary(recent)
            valid_summary = self.validate_and_format_summary(raw_summary)

            if valid_summary:
                conversation_service.update_summary(conversation_id, valid_summary)
                logger.info(f"[OK] SummaryService: summary saved for {conversation_id}")

        except Exception as exc:
            logger.warning(f"⚠️ SummaryService maybe_update_summary failed | {exc}")
