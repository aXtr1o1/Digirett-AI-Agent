"""
api/routes/invite.py
====================
Public endpoints for the invitation flow.
No authentication required — these are hit BEFORE the user has a Clerk account.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional

router = APIRouter(prefix="/invite", tags=["Invite"])

# ── Service reference ────────────────────────────────────────
_supabase = None

def set_services(supabase_client):
    global _supabase
    _supabase = supabase_client


# ── Routes ───────────────────────────────────────────────────

@router.get("/verify")
async def verify_invite_token(token: str):
    """
    Called by the frontend /invite page to validate the invite token.
    Returns the role and masked email so the frontend can guide the user.

    Flow:
      1. Frontend /invite page loads with ?token=...
      2. Frontend calls GET /api/v1/invite/verify?token=...
      3. This endpoint checks role_invites table
      4. Returns { valid: true, role: "lawyer", email: "s****@axtr.in" }
      5. Frontend shows "You were invited as a Lawyer. Sign up to continue."
      6. Frontend redirects user to Clerk signup/signin
    """
    if not token:
        raise HTTPException(status_code=400, detail="Token is required.")

    try:
        resp = _supabase.table("role_invites") \
            .select("email, role, status") \
            .eq("token", token) \
            .execute()

        if not resp.data:
            raise HTTPException(
                status_code=404,
                detail="Invitation not found. It may have expired or already been used."
            )

        invite = resp.data[0]

        if invite["status"] == "accepted":
            return {
                "valid": False,
                "reason": "already_accepted",
                "message": "This invitation has already been used. Please sign in instead."
            }

        if invite["status"] == "expired":
            return {
                "valid": False,
                "reason": "expired",
                "message": "This invitation has expired. Please ask an admin to resend."
            }

        # Mask email for display: "sabari@axtr.in" -> "s****@axtr.in"
        email = invite["email"]
        local, domain = email.split("@", 1)
        masked_email = local[0] + "****@" + domain

        return {
            "valid": True,
            "role": invite["role"],
            "masked_email": masked_email,
            "token": token,
            "message": f"You have been invited as a {invite['role'].capitalize()}. Sign up to activate your account."
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to verify invite: {exc}")