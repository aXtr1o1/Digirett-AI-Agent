"""
services/rating_service.py — Consultation Ratings Service

Encapsulates database operations for feedback ratings and lawyer rating logs.
"""

import logging
from typing import Any, Dict, List, Optional

from config import settings
from services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class RatingService:

    def __init__(self, supabase_client, notification_service: Optional[NotificationService] = None) -> None:
        self._supabase = supabase_client
        self._notification_service = notification_service
        logger.info("[OK] RatingService initialized")

    def submit_rating(
        self,
        internal_user_id: str,
        ticket_id: str,
        rating: int,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validates ticket ownership, state, inserts rating row, and triggers notification."""
        # 1. Fetch ticket to verify ownership and assigned lawyer
        ticket_resp = (
            self._supabase.table("hitl_tickets")
            .select("ticket_id, user_id, status, assigned_lawyer_id")
            .eq("ticket_id", ticket_id)
            .execute()
        )

        if not ticket_resp.data:
            raise ValueError("Ticket not found.")

        ticket = ticket_resp.data[0]

        # Ownership check
        if ticket.get("user_id") != internal_user_id:
            raise PermissionError("Access denied. You can only rate your own tickets.")

        # Ticket status check
        status_str = ticket.get("status", "").lower()
        if status_str not in ("resolved", "closed"):
            raise ValueError("You can only rate tickets that are resolved or closed.")

        lawyer_id = ticket.get("assigned_lawyer_id")
        if not lawyer_id:
            raise ValueError("This ticket does not have an assigned lawyer to rate.")

        # Insert / Upsert rating row
        insert_query = self._supabase.table("consultation_ratings").upsert({
            "ticket_id": ticket_id,
            "user_id": internal_user_id,
            "lawyer_id": lawyer_id,
            "rating": rating,
            "comment": comment,
        }, on_conflict="ticket_id")

        self._supabase.execute_query(insert_query)
        logger.info(f"💾 Consultation rating saved | ticket={ticket_id} | rating={rating}")

        return {
            "lawyer_id": lawyer_id,
            "status": "success",
            "message": "Feedback submitted successfully.",
        }

    async def send_rating_notification_task(
        self,
        ticket_id: str,
        lawyer_id: str,
        rating: int,
        comment: Optional[str] = None,
    ) -> None:
        """Invokes NotificationService to send email alert."""
        if self._notification_service:
            await self._notification_service.send_rating_notification(
                ticket_id=ticket_id,
                lawyer_id=lawyer_id,
                rating=rating,
                comment=comment,
            )

    def get_lawyer_ratings(self, lawyer_id: str) -> List[Dict[str, Any]]:
        """Fetch rating logs for a specific lawyer."""
        resp = (
            self._supabase.table("consultation_ratings")
            .select("rating_id, rating, comment, created_at, ticket_id")
            .eq("lawyer_id", lawyer_id)
            .execute()
        )
        return resp.data or []

    def get_admin_ratings(self) -> List[Dict[str, Any]]:
        """Fetch all consultation ratings with lawyer metadata for admin audit."""
        resp = (
            self._supabase.table("consultation_ratings")
            .select("*, users!consultation_ratings_lawyer_id_fkey(user_name, email)")
            .order("created_at", desc=True)
            .execute()
        )

        ratings_list = []
        for row in resp.data or []:
            lawyer_meta = row.get("users") or {}
            ratings_list.append({
                "rating_id": str(row.get("rating_id", "")),
                "ticket_id": str(row.get("ticket_id", "")),
                "user_id": str(row.get("user_id", "")),
                "lawyer_id": str(row.get("lawyer_id", "")),
                "rating": int(row.get("rating", 5)),
                "comment": row.get("comment"),
                "created_at": str(row.get("created_at", "")),
                "lawyer_name": lawyer_meta.get("user_name"),
                "lawyer_email": lawyer_meta.get("email"),
            })
        return ratings_list
