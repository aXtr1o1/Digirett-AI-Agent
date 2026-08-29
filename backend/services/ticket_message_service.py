"""
services/ticket_message_service.py — Pre-consultation Ticket Messaging Service

Encapsulates database operations and authorization checks for HITL ticket message threads.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class TicketMessageService:

    def __init__(self, supabase_client, notification_service: Optional[NotificationService] = None) -> None:
        self._supabase = supabase_client
        self._notification_service = notification_service
        logger.info("[OK] TicketMessageService initialized")

    def validate_ticket_access(
        self,
        ticket_id: str,
        internal_user_id: str,
        user_role: str,
    ) -> Dict[str, Any]:
        """Validates that the ticket exists and user is authorized (owner, assigned lawyer, or admin)."""
        ticket_resp = (
            self._supabase.table("hitl_tickets")
            .select("ticket_id, user_id, assigned_lawyer_id, status")
            .eq("ticket_id", ticket_id)
            .execute()
        )

        if not ticket_resp.data or len(ticket_resp.data) == 0:
            raise ValueError("Ticket not found.")

        ticket = ticket_resp.data[0]

        if user_role in ("admin", "system_admin"):
            return ticket

        if user_role == "lawyer":
            if ticket.get("assigned_lawyer_id") != internal_user_id:
                raise PermissionError("Unauthorized. You are not the assigned lawyer for this ticket.")
            return ticket

        if ticket.get("user_id") != internal_user_id:
            raise PermissionError("Unauthorized. You do not own this ticket.")

        return ticket

    def get_messages(
        self,
        ticket_id: str,
        internal_user_id: str,
        user_role: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fetch messages for a ticket thread with optional pagination."""
        self.validate_ticket_access(ticket_id, internal_user_id, user_role)

        resp = (
            self._supabase.table("ticket_messages")
            .select("*")
            .eq("ticket_id", ticket_id)
            .order("created_at", desc=False)
            .range(offset, offset + limit - 1)
            .execute()
        )

        return resp.data or []

    def create_message(
        self,
        ticket_id: str,
        sender_id: str,
        sender_role: str,
        content: str,
        file_name: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a new message into the ticket thread."""
        self.validate_ticket_access(ticket_id, sender_id, sender_role)

        payload = {
            "ticket_id": ticket_id,
            "sender_id": sender_id,
            "sender_role": sender_role,
            "content": content,
            "file_name": file_name,
            "document_id": document_id,
            "is_read": False,
        }

        resp = self._supabase.table("ticket_messages").insert(payload).execute()
        if not resp.data or len(resp.data) == 0:
            raise RuntimeError("Failed to insert ticket message into database.")

        logger.info(f"💾 Ticket message created | ticket={ticket_id} | sender={sender_id}")
        return resp.data[0]

    async def send_message_notification_task(
        self,
        ticket_id: str,
        sender_id: str,
        sender_role: str,
        message_content: str,
    ) -> None:
        """Delegates background email dispatching to NotificationService."""
        if self._notification_service:
            await self._notification_service.send_ticket_message_notification(
                ticket_id=ticket_id,
                sender_id=sender_id,
                sender_role=sender_role,
                message_content=message_content,
            )

    def mark_messages_read(
        self,
        ticket_id: str,
        internal_user_id: str,
        user_role: str,
    ) -> int:
        """Marks unread messages sent by the opposite party as read."""
        self.validate_ticket_access(ticket_id, internal_user_id, user_role)
        opposite_role = "lawyer" if user_role == "user" else "user"

        resp = (
            self._supabase.table("ticket_messages")
            .update({"is_read": True})
            .eq("ticket_id", ticket_id)
            .eq("sender_role", opposite_role)
            .eq("is_read", False)
            .execute()
        )

        count = len(resp.data) if resp.data else 0
        logger.info(f"READ: Marked {count} unread messages as read | ticket={ticket_id}")
        return count
