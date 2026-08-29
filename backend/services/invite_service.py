"""
services/invite_service.py — Public Invitation Token Service

Handles invitation token verification, defensive email masking, and role invite lifecycle logic.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def mask_email(email: str) -> str:
    """
    Defensive email masking utility.
    Examples:
      'sabari@axtr.in' -> 's****@axtr.in'
      'a@b.com'        -> '*@b.com'
    """
    if not email or "@" not in email:
        return "****"
    local, domain = email.split("@", 1)
    if not local:
        return f"****@{domain}"
    if len(local) <= 1:
        masked_local = "*" * len(local)
    else:
        masked_local = local[0] + "****"
    return f"{masked_local}@{domain}"



class InviteService:

    def __init__(self, supabase_client) -> None:
        self._supabase = supabase_client
        logger.info("[OK] InviteService initialized")

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Queries role_invites by token and evaluates status.
        Returns a dict matching InviteVerificationResponse attributes.
        """
        if not self._supabase:
            raise RuntimeError("Database connection unavailable in InviteService.")

        resp = (
            self._supabase.table("role_invites")
            .select("email, role, status")
            .eq("token", token)
            .execute()
        )

        if not resp.data or len(resp.data) == 0:
            return {
                "valid": False,
                "reason": "not_found",
                "message": "Invitation not found. It may have expired or already been used.",
            }

        invite = resp.data[0]
        status_str = invite.get("status", "").lower()

        if status_str == "accepted":
            return {
                "valid": False,
                "reason": "already_accepted",
                "message": "This invitation has already been used. Please sign in instead.",
            }

        if status_str == "expired":
            return {
                "valid": False,
                "reason": "expired",
                "message": "This invitation has expired. Please ask an admin to resend.",
            }

        role = invite.get("role", "user")
        masked = mask_email(invite.get("email", ""))
        role_title = role.capitalize()

        return {
            "valid": True,
            "role": role,
            "masked_email": masked,
            "message": f"You have been invited as a {role_title}. Sign up to activate your account.",
        }
