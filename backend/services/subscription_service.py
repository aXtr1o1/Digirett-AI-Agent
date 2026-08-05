"""
services/subscription_service.py — Subscription Management Service

Centralizes Stripe subscription plan synchronization and plan tier mappings.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

PLAN_MAPPING = {
    "start_up": "start_up",
    "vekst":    "vekst",
    "smb":      "smb",
    "enterprise": "enterprise",
}


class SubscriptionService:

    def __init__(self, user_service, supabase_client=None) -> None:
        self._user_service = user_service
        self._supabase = supabase_client or (user_service._supabase if user_service else None)
        logger.info("[OK] SubscriptionService initialized")

    def resolve_plan_tier(self, product_name: str) -> str:
        """Centralized helper to map product name string to plan tier."""
        name_lower = (product_name or "").lower()
        for key, plan in PLAN_MAPPING.items():
            if key in name_lower:
                return plan
        return "free_trial"

    def sync_user_plan(self, clerk_user_id: str, plan_tier: str, role: Optional[str] = None) -> bool:
        """Consolidates plan tier updates across Supabase database and Clerk metadata."""
        if not self._user_service or not self._supabase:
            logger.error(" SubscriptionService missing dependencies for plan sync.")
            return False

        assigned_role = role or plan_tier

        # 1. Update Supabase database
        try:
            update_query = (
                self._supabase.table("users")
                .update({
                    "plan_tier": plan_tier,
                    "role": assigned_role,
                    "updated_at": datetime.utcnow().isoformat(),
                })
                .eq("clerk_user_id", clerk_user_id)
            )
            self._supabase.execute_query(update_query)
            logger.info(f" DB plan_tier updated to '{plan_tier}' for Clerk ID: {clerk_user_id}")
        except Exception as db_exc:
            logger.error(f" Supabase update failed for user {clerk_user_id}: {db_exc}")
            return False

        # 2. Update Clerk Metadata
        try:
            self._user_service._sync_clerk_metadata(clerk_user_id, {
                "role": assigned_role,
                "plan_tier": plan_tier,
            })
            logger.info(f" Clerk metadata updated to '{plan_tier}' for user {clerk_user_id}")
        except Exception as clerk_exc:
            logger.error(f" Clerk metadata update failed for user {clerk_user_id}: {clerk_exc}")

        return True
