from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr

from core.auth import ClerkUser, require_db_role
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
    current_admin: ClerkUser = Depends(require_db_role("admin"))
):
    """
    Admin invites a new user via email. 
    A pending invite is created in role_invites and an email is sent.
    """
    if req.role not in ["lawyer", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'lawyer' or 'admin'.")
    
    # Get internal admin ID and email
    admin_id = _user_service.get_user_id_from_clerk_id(current_admin.clerk_user_id)
    admin_email = current_admin.email
    
    success = await _user_service.invite_user(
        email=req.email,
        role=req.role,
        admin_id=admin_id,
        email_service=_email_service,
        admin_email=admin_email
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send invitation.")
        
    return {"message": f"Invitation sent to {req.email}"}

@router.post("/promote/lawyer")
async def promote_to_lawyer(
    req: PromoteLawyerRequest,
    current_admin: ClerkUser = Depends(require_db_role("admin"))
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
    current_admin: ClerkUser = Depends(require_db_role("admin"))
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
    current_admin: ClerkUser = Depends(require_db_role("admin"))
):
    """Lists all users in the system."""
    try:
        # Fetch directly from user_service or supabase, ordered by newest first
        response = _user_service._supabase.table("users").select("*, user_profiles(display_name)").order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/invitations")
async def list_invitations(
    current_admin: ClerkUser = Depends(require_db_role("admin"))
):
    """Lists all team invitations."""
    invites = _user_service.get_invitations()
    return invites

@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = 50,
    offset: int = 0,
    current_admin: ClerkUser = Depends(require_db_role("admin"))
):
    """Fetches global audit logs for administrative oversight."""
    logs = _user_service.get_audit_logs(limit=limit, offset=offset)
    return logs

@router.patch("/tickets/{ticket_id}/assign/{lawyer_id}")
async def admin_assign_ticket(
    ticket_id: str,
    lawyer_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin"))
):
    """Admin assigns an open ticket to a specific lawyer."""
    from main import hitl_service
    success = hitl_service.assign_ticket(ticket_id, lawyer_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to assign ticket. Make sure it is open.")
    return {"status": "success", "message": f"Ticket {ticket_id} assigned to lawyer {lawyer_id}"}

@router.patch("/tickets/{ticket_id}/close")
async def admin_close_ticket(
    ticket_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin"))
):
    """Admin closes a resolved ticket."""
    from main import hitl_service
    from datetime import datetime
    try:
        hitl_service._supabase.table("hitl_tickets").update({
            "status": "closed",
            "closed_at": datetime.utcnow().isoformat()
        }).eq("ticket_id", ticket_id).execute()
        return {"status": "success", "message": "Ticket closed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/users/{user_id}/demote")
async def admin_demote_user(
    user_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin"))
):
    """Admin demotes a lawyer back to a standard user."""
    from main import user_service
    try:
        user_info = user_service.get_user_by_id(user_id)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
            
        user_service._supabase.table("users").update({"role": "user"}).eq("user_id", user_id).execute()
        user_service._sync_clerk_role(user_info["clerk_user_id"], "user")
        
        # Optionally remove from lawyer_profiles, but keeping it is fine (they just lose the role)
        
        return {"status": "success", "message": "User demoted to standard user."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/users/{user_id}/suspend")
async def admin_suspend_user(
    user_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin"))
):
    """Admin suspends an account."""
    from main import user_service
    try:
        user_service._supabase.table("users").update({"status": "inactive"}).eq("user_id", user_id).execute()
        return {"status": "success", "message": "User suspended."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
