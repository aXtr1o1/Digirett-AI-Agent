"""
services/webhook_service.py — Webhook Ingestion Service

Handles Clerk user event webhooks and Stripe subscription webhook events with idempotency checks.
"""

import logging
from typing import Any, Dict, Optional, Set

from services.subscription_service import SubscriptionService
from services.user_service import UserService
from services.email_service import EmailService

logger = logging.getLogger(__name__)


class WebhookService:

    def __init__(
        self,
        user_service: UserService,
        subscription_service: SubscriptionService,
        email_service: Optional[EmailService] = None,
    ) -> None:
        self._user_service = user_service
        self._subscription_service = subscription_service
        self._email_service = email_service
        self._processed_events: Set[str] = set()
        logger.info("[OK] WebhookService initialized")

    def is_event_processed(self, event_id: str) -> bool:
        """Check idempotency layer for processed webhook event IDs."""
        if not event_id:
            return False
        return event_id in self._processed_events

    def mark_event_processed(self, event_id: str) -> None:
        """Record processed event ID to prevent duplicate handling."""
        if event_id:
            self._processed_events.add(event_id)
            if len(self._processed_events) > 5000:
                self._processed_events.clear()

    async def handle_clerk_event(self, evt: Dict[str, Any], event_id: Optional[str] = None) -> Dict[str, Any]:
        """Process Clerk webhook events (user.created, email.created)."""
        if event_id and self.is_event_processed(event_id):
            logger.info(f"🔄 Webhook event already processed (idempotent ignore): {event_id}")
            return {"status": "ignored", "reason": "Already processed"}

        event_type = evt.get("type")
        data = evt.get("data", {})

        if event_type == "user.created":
            clerk_user_id = data.get("id")
            email_addresses = data.get("email_addresses", [])
            primary_email_id = data.get("primary_email_address_id")
            email = ""
            for ea in email_addresses:
                if ea.get("id") == primary_email_id:
                    email = ea.get("email_address")
                    break
            if not email and email_addresses:
                email = email_addresses[0].get("email_address", "")

            display_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or data.get("username", "") or (email.split("@")[0] if email else "User")

            if self._user_service.user_exists(clerk_user_id):
                return {"status": "ignored", "reason": "User already exists"}

            self._user_service.create_user_from_webhook(
                clerk_user_id=clerk_user_id,
                email=email,
                tenant_id="00000000-0000-0000-0000-000000000000",
                display_name=display_name,
                username=data.get("username", ""),
            )
            if event_id:
                self.mark_event_processed(event_id)
            return {"status": "success", "message": "User created"}

        return {"status": "ignored", "reason": f"Unhandled event type: {event_type}"}

    def sync_stripe_subscription(self, clerk_user_id: str, item_name: str, event_id: Optional[str] = None) -> Dict[str, Any]:
        """Delegates Stripe subscription plan synchronization to SubscriptionService."""
        if event_id and self.is_event_processed(event_id):
            logger.info(f"🔄 Stripe event already processed (idempotent ignore): {event_id}")
            return {"status": "ignored", "reason": "Already processed"}

        plan_tier = self._subscription_service.resolve_plan_tier(item_name)
        success = self._subscription_service.sync_user_plan(clerk_user_id, plan_tier)

        if success and event_id:
            self.mark_event_processed(event_id)

        return {"status": "success" if success else "error", "message": f"Plan synced to '{plan_tier}'"}
