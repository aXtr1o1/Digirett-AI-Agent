from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from core.auth import ClerkUser, require_role, require_db_role
from services.hitl_service import HitlService
from services.user_service import UserService

router = APIRouter(prefix="/hitl", tags=["HITL Escalation"])

# ── Services ─────────────────────────────────────────────────────────
_hitl_service: Optional[HitlService] = None
_user_service: Optional[UserService] = None

def set_services(hitl_svc: HitlService, user_svc: UserService):
    global _hitl_service, _user_service
    _hitl_service = hitl_svc
    _user_service = user_svc

# ── Schemas ─────────────────────────────────────────────────────────

class EscalateRequest(BaseModel):
    conversation_id: str
    trigger_message_id: str
    user_note: Optional[str] = None

class RespondRequest(BaseModel):
    content: str

# ── Routes ─────────────────────────────────────────────────────────

@router.post("/escalate")
async def escalate_conversation(
    req: EscalateRequest,
    current_user: ClerkUser = Depends(require_db_role("user", "lawyer", "admin"))
):
    """
    User triggers an escalation for a specific conversation.
    """
    user_id = _user_service.get_user_id_from_clerk_id(current_user.clerk_user_id)
    
    ticket = _hitl_service.create_ticket(
        conversation_id=req.conversation_id,
        user_id=user_id,
        trigger_message_id=req.trigger_message_id,
        user_note=req.user_note
    )
    
    return {"message": "Escalation ticket created successfully.", "ticket_id": ticket["ticket_id"]}

@router.get("/queue")
async def get_ticket_queue(
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin"))
):
    """
    Lawyers view the shared queue of 'open' tickets.
    """
    tickets = _hitl_service.get_open_tickets()
    return tickets

@router.patch("/tickets/{ticket_id}/assign")
async def assign_ticket(
    ticket_id: str,
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin"))
):
    """
    Lawyer self-assigns a ticket from the queue.
    """
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    
    success = _hitl_service.assign_ticket(ticket_id, lawyer_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to assign ticket. It might already be claimed.")
        
    return {"message": "Ticket assigned successfully."}

@router.get("/tickets/{ticket_id}/details")
async def get_ticket_details(
    ticket_id: str,
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin"))
):
    """
    Lawyer views full ticket details including user info.
    Only the assigned lawyer can see this.
    """
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    
    details = _hitl_service.get_ticket_with_user_details(ticket_id, lawyer_id)
    if not details:
        raise HTTPException(status_code=403, detail="Unauthorized. You must be the assigned lawyer.")
        
    return details

@router.post("/tickets/{ticket_id}/respond")
async def respond_to_ticket(
    ticket_id: str,
    req: RespondRequest,
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin"))
):
    """
    Lawyer submits a written response to the user's escalation.
    """
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    
    # Verify assignment first
    details = _hitl_service.get_ticket_with_user_details(ticket_id, lawyer_id)
    if not details:
        raise HTTPException(status_code=403, detail="Unauthorized. You must be the assigned lawyer.")
    
    success = _hitl_service.respond_to_ticket(ticket_id, lawyer_id, req.content)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save response.")
        
    return {"message": "Response submitted and ticket resolved."}

@router.get("/my-tickets")
async def get_my_tickets(
    current_user: ClerkUser = Depends(require_db_role("user", "lawyer", "admin"))
):
    """
    User views their own escalation tickets and their status.
    """
    user_id = _user_service.get_user_id_from_clerk_id(current_user.clerk_user_id)
    tickets = _hitl_service.get_user_tickets(user_id)
    return tickets

@router.get("/my-resolved-tickets")
async def get_my_resolved_history(
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin"))
):
    """
    Lawyer views their own history of resolved tickets.
    """
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    tickets = _hitl_service.get_lawyer_resolved_history(lawyer_id)
    return tickets
