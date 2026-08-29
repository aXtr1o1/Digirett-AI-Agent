"""
services/notification_service.py — Notification Service

Encapsulates email notification dispatching for consultation ratings, ticket messages,
and admin QA alerts.
"""

import logging
from typing import Optional

from config import settings
from services.email_service import EmailService

logger = logging.getLogger(__name__)


class NotificationService:

    def __init__(self, email_service: Optional[EmailService] = None, supabase_client=None) -> None:
        self._email_service = email_service
        self._supabase = supabase_client
        logger.info("[OK] NotificationService initialized")

    async def send_ticket_message_notification(
        self,
        ticket_id: str,
        sender_id: str,
        sender_role: str,
        message_content: str,
    ) -> bool:
        """Sends background email notification to recipient when a new ticket message is sent."""
        if not self._email_service or not self._supabase:
            logger.warning("⚠️ NotificationService dependencies missing. Skipping ticket message email.")
            return False

        try:
            # 1. Fetch ticket details
            ticket_resp = (
                self._supabase.table("hitl_tickets")
                .select("user_id, assigned_lawyer_id")
                .eq("ticket_id", ticket_id)
                .single()
                .execute()
            )

            if not ticket_resp.data:
                return False

            ticket = ticket_resp.data
            recipient_id = (
                ticket.get("assigned_lawyer_id") if sender_role == "user" else ticket.get("user_id")
            )

            if not recipient_id:
                logger.warning(f"⚠️ No recipient found for ticket message notification | ticket={ticket_id}")
                return False

            # 2. Fetch recipient email
            user_resp = (
                self._supabase.table("users")
                .select("email, user_name, user_profiles(display_name)")
                .eq("user_id", recipient_id)
                .single()
                .execute()
            )

            if not user_resp.data:
                return False

            user_data = user_resp.data
            recipient_email = user_data.get("email")
            profile = user_data.get("user_profiles") or {}
            recipient_name = profile.get("display_name") or user_data.get("user_name") or "User"

            if not recipient_email:
                return False

            sender_title = "User" if sender_role == "user" else "Lawyer"
            subject = f"New message on Ticket #{ticket_id[:8]}"
            preview = message_content[:150] + "..." if len(message_content) > 150 else message_content

            html_body = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>New Message from {sender_title}</h2>
                <p>Hello {recipient_name},</p>
                <p>You have received a new message regarding consultation ticket <b>#{ticket_id[:8]}</b>:</p>
                <blockquote style="background: #f9f9f9; padding: 10px; border-left: 3px solid #0070f3;">
                    {preview}
                </blockquote>
                <p>Please log in to your Digirett dashboard to reply.</p>
            </div>
            """

            return await self._email_service.send_clerk_email(
                to_email=recipient_email,
                subject=subject,
                html_content=html_body,
                plain_content=f"New message from {sender_title}: {preview}",
            )

        except Exception as exc:
            logger.error(f"❌ Failed to send ticket message notification | ticket={ticket_id} | {exc}")
            return False

    async def send_rating_notification(
        self,
        ticket_id: str,
        lawyer_id: str,
        rating: int,
        comment: Optional[str] = None,
    ) -> bool:
        """Notifies assigned lawyer of feedback and alerts admin if rating <= LOW_RATING_THRESHOLD."""
        if not self._email_service or not self._supabase:
            logger.warning("⚠️ NotificationService dependencies missing. Skipping rating email.")
            return False

        try:
            lawyer_resp = (
                self._supabase.table("users")
                .select("email, user_name, user_profiles(display_name)")
                .eq("user_id", lawyer_id)
                .single()
                .execute()
            )

            if lawyer_resp.data:
                lawyer_data = lawyer_resp.data
                to_email = lawyer_data.get("email")
                profile = lawyer_data.get("user_profiles") or {}
                lawyer_name = profile.get("display_name") or lawyer_data.get("user_name") or "Lawyer"

                if to_email:
                    await self._email_service.send_consultation_feedback_email(
                        to_email=to_email,
                        lawyer_name=lawyer_name,
                        ticket_id=ticket_id,
                        rating=rating,
                        comment=comment,
                    )

                admin_email = getattr(settings, "ADMIN_ALERT_EMAIL", None)
                low_threshold = getattr(settings, "LOW_RATING_THRESHOLD", 2)

                if rating <= low_threshold and admin_email:
                    await self._email_service.send_consultation_feedback_email(
                        to_email=admin_email,
                        lawyer_name=f"{lawyer_name} (Admin Review)",
                        ticket_id=ticket_id,
                        rating=rating,
                        comment=f"[QA REVIEW REQUIRED] {comment or 'No comment provided.'}",
                    )

            return True

        except Exception as exc:
            logger.warning(f"⚠️ Failed to send rating notification email | {exc}")
            return False
