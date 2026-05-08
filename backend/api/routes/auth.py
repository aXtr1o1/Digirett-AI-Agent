from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import ClerkUser, require_db_role
from services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])

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
    # Import inside to avoid circular dependency if user_service is global
    from main import user_service
    
    success = user_service.accept_invite(
        token=req.token, 
        clerk_user_id=current_user.clerk_user_id,
        email=current_user.email
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Invalid, expired, or mismatched invitation token.")
        
    return {"status": "success", "message": "Invitation accepted. Role updated."}
