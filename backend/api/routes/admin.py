from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr

from core.auth import ClerkUser, require_role
from services.user_service import UserService
from services.email_service import EmailService

router = APIRouter(prefix="/admin", tags=["Admin"])

# ── Services ─────────────────────────────────────────────────────────
_user_service: Optional[UserService] = None
_email_service: Optional[EmailService] = None

def set_services(user_svc: UserService, email_svc: EmailService):
    global _user_service, _email_service
    _user_service = user_svc
    _email_service = email_svc

# ── Schemas ─────────────────────────────────────────────────────────

class InviteRequest(BaseModel):
    email: EmailStr
    role: str # 'lawyer', 'admin'

class PromoteLawyerRequest(BaseModel):
    user_id: str
    bar_license: Optional[str] = None
    bar_council: Optional[str] = None

class PromoteAdminRequest(BaseModel):
    user_id: str
    full_name: Optional[str] = None

# ── Routes ─────────────────────────────────────────────────────────

@router.post("/invite")
async def invite_user(
    req: InviteRequest,
    current_admin: ClerkUser = Depends(require_role("admin"))
):
    """
    Admin invites a new user via email. 
    A pending invite is created in role_invites and an email is sent.
    """
    if req.role not in ["lawyer", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'lawyer' or 'admin'.")
    
    # Get internal admin ID
    admin_id = _user_service.get_user_id_from_clerk_id(current_admin.clerk_user_id)
    
    success = _user_service.invite_user(
        email=req.email,
        role=req.role,
        admin_id=admin_id,
        email_service=_email_service
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send invitation.")
        
    return {"message": f"Invitation sent to {req.email}"}

@router.post("/promote/lawyer")
async def promote_to_lawyer(
    req: PromoteLawyerRequest,
    current_admin: ClerkUser = Depends(require_role("admin"))
):
    """Promotes an existing user to the Lawyer role."""
    admin_id = _user_service.get_user_id_from_clerk_id(current_admin.clerk_user_id)
    
    success = _user_service.promote_to_lawyer(
        user_id=req.user_id,
        admin_id=admin_id,
        bar_license=req.bar_license,
        bar_council=req.bar_council
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to promote user to lawyer.")
        
    return {"message": "User promoted to lawyer successfully."}

@router.post("/promote/admin")
async def promote_to_admin(
    req: PromoteAdminRequest,
    current_admin: ClerkUser = Depends(require_role("admin"))
):
    """Promotes an existing user to the Admin role."""
    admin_id = _user_service.get_user_id_from_clerk_id(current_admin.clerk_user_id)
    
    success = _user_service.promote_to_admin(
        user_id=req.user_id,
        admin_id=admin_id,
        full_name=req.full_name
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to promote user to admin.")
        
    return {"message": "User promoted to admin successfully."}

@router.get("/users")
async def list_users(
    current_admin: ClerkUser = Depends(require_role("admin"))
):
    """Lists all users in the system."""
    try:
        # Fetch directly from user_service or supabase
        response = _user_service._supabase.table("users").select("*, user_profiles(display_name)").execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
