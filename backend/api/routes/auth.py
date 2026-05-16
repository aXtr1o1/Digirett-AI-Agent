from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import ClerkUser, require_db_role
from services.user_service import UserService
from typing import Optional

router = APIRouter(prefix="/auth", tags=["auth"])

_user_service: Optional[UserService] = None

def set_services(user_service: UserService) -> None:
    global _user_service
    _user_service = user_service

class AcceptInviteRequest(BaseModel):
    token: str

@router.post("/accept-invite")
async def accept_invite(
    req: AcceptInviteRequest,
    current_user: ClerkUser = Depends(require_db_role("user", "lawyer", "admin"))
):
    """
    User accepts an invitation using the token from their email.
    If they are already logged in, this upgrades their role immediately.
    """
    if not _user_service:
        raise HTTPException(status_code=500, detail="UserService not initialized")
        
    success = _user_service.accept_invite(
        token=req.token, 
        clerk_user_id=current_user.clerk_user_id,
        email=current_user.email
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Invalid, expired, or mismatched invitation token.")
        
    return {"status": "success", "message": "Invitation accepted. Role updated."}
