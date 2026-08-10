import logging
from typing import Optional, Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.auth import ClerkUser, require_db_role
from schemas.requests import AcceptInviteRequest
from schemas.responses import AcceptInviteResponse
from services.user_service import UserService, AcceptInviteResult



logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

def get_user_service(request: Request) -> UserService:
    svc = getattr(request.app.state, "user_service", None)
    if svc is None:
        raise RuntimeError("UserService is not initialized on application state.")
    return svc

@router.post(
    "/accept-invite",
    summary="Accept a role invitation",
    response_model=AcceptInviteResponse,
)
async def accept_invite(
    req: AcceptInviteRequest,
    current_user: ClerkUser = Depends(require_db_role("user", "lawyer", "admin")),
    user_service: UserService = Depends(get_user_service),
):
    """
    User accepts an invitation using the UUID token from their email.
    Upgrades their system role upon successful verification.
    """
    logger.info(
        f"Processing invitation acceptance attempt | user={current_user.clerk_user_id} | token={req.token[:8]}..."
    )

    result: AcceptInviteResult = await user_service.accept_invite(
        token=req.token,
        clerk_user_id=current_user.clerk_user_id,
        email=current_user.email or "",
    )

    if not result.success:
        logger.warning(
            f"Invitation acceptance failed | status={result.status_code} | detail={result.detail}",
            extra={"user": current_user.clerk_user_id, "token": req.token[:8]}
        )
        raise HTTPException(status_code=result.status_code, detail=result.detail)

    logger.info(
        "Invitation accepted successfully",
        extra={
            "user": current_user.clerk_user_id,
            "role": result.role,
            "invited_by": result.invited_by,
        }
    )

    return AcceptInviteResponse(
        status="success",
        message="Invitation accepted. Role updated.",
        role=result.role,
    )
