"""
api/routes/invite.py — Public endpoints for the invitation flow.

Refactored according to TL code review guidelines:
- Pure FastAPI Dependency Injection via Request.app.state
- Zero direct Supabase / database queries in controller routes
- Delegated token lookup & status evaluation to InviteService
- Defensive email masking utility (mask_email)
- Pydantic InviteVerificationResponse schema without raw token exposure
- Clean error logging with logger.exception
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from schemas.responses import InviteVerificationResponse
from services.invite_service import InviteService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/invite", tags=["Invite"])


def get_invite_service(request: Request) -> InviteService:
    svc = getattr(request.app.state, "invite_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="InviteService is not initialized on application state.",
        )
    return svc


@router.get(
    "/verify",
    response_model=InviteVerificationResponse,
    summary="Validate invitation token and return role + masked email",
)
async def verify_invite_token(
    token: str,
    invite_service: InviteService = Depends(get_invite_service),
):
    """
    Called by frontend /invite page to validate an invite token.
    Returns validity, role, and defensively masked email.
    """
    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token is required.",
        )

    try:
        result = invite_service.verify_token(token.strip())
        if not result["valid"] and result.get("reason") == "not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result["message"],
            )

        return InviteVerificationResponse(**result)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"❌ Failed to verify invite token: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify invitation token.",
        )