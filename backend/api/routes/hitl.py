"""
api/routes/hitl.py — Human-in-the-Loop escalation endpoints

Endpoints:
  POST /hitl/escalate                        — User creates an escalation ticket
  GET  /hitl/queue                           — Lawyer views open ticket queue (with summary)
  PATCH /hitl/tickets/{id}/assign            — Lawyer self-assigns ticket (race-condition safe)
  GET  /hitl/tickets/{id}/details            — Assigned lawyer views full ticket details
  POST /hitl/tickets/{id}/respond            — Lawyer resolves ticket with response + outcome notes
  GET  /hitl/my-tickets                      — User views their own tickets
  GET  /hitl/my-resolved-tickets             — Lawyer views their resolved history
  GET  /hitl/status/{conversation_id}        — Check if conversation is escalated
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel

from core.auth import ClerkUser, require_db_role
from services.email_service import EmailService
from services.hitl_service import HitlService
from services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hitl", tags=["HITL Escalation"])

# ── Services ─────────────────────────────────────────────────────────
_hitl_service: Optional[HitlService] = None
_user_service: Optional[UserService] = None
_email_service: Optional[EmailService] = None


def set_services(
    hitl_svc: HitlService,
    user_svc: UserService,
    email_svc: Optional[EmailService] = None,
) -> None:
    global _hitl_service, _user_service, _email_service
    _hitl_service = hitl_svc
    _user_service = user_svc
    _email_service = email_svc


# ── Schemas ───────────────────────────────────────────────────────────

class EscalateRequest(BaseModel):
    conversation_id: str
    trigger_message_id: str
    user_note: Optional[str] = None


class RespondRequest(BaseModel):
    content: str
    outcome_notes: Optional[str] = None  # Phase 8: optional outcome notes


class NoShowRequest(BaseModel):
    outcome_notes: Optional[str] = None
    no_show_type: str = "user" # "user" or "both"


@router.get(
    "/check-status",
    summary="Publicly check if a user is suspended (before login)",
)
async def check_user_status(identifier: str):
    """
    Checks if a user is suspended based on email or username.
    Publicly accessible to allow the login form to block restricted users.
    """
    try:
        from db.supabase_client import get_supabase
        supabase = get_supabase()
        
        # Check by email or username (case-insensitive first)
        resp = supabase.table("users") \
            .select("status, user_name, email") \
            .or_(f"email.ilike.{identifier},user_name.ilike.{identifier}") \
            .limit(1) \
            .execute()
            
        if resp.data:
            user_record = resp.data[0]
            user_status = user_record.get("status")
            db_user_name = user_record.get("user_name")
            db_email = user_record.get("email")
            
            # Enforce case sensitivity for username
            if db_user_name and db_user_name.lower() == identifier.lower():
                if db_user_name != identifier:
                    return {"status": "case_mismatch", "is_suspended": False}
                    
            return {"status": user_status, "is_suspended": user_status == "suspended"}
        
        return {"status": "not_found", "is_suspended": False}
    except Exception as exc:
        logger.error(f"❌ check_user_status failed | {exc}")
        return {"status": "error", "is_suspended": False}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ESCALATION (User)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "/escalate",
    summary="User triggers escalation for a conversation",
)
async def escalate_conversation(
    req: EscalateRequest,
    current_user: ClerkUser = Depends(require_db_role("user", "lawyer", "admin")),
):
    """
    Phase 1: User clicks "Talk to a Lawyer" in the chat.

    Creates an escalation ticket. The ticket will automatically include:
    - The latest AI-generated conversation summary (from conversations.conversation_summary)
    - The user's profile (display_name, email, phone)

    No practice area selection — lawyers see the case brief from the DB summary.
    """
    user_id = _user_service.get_user_id_from_clerk_id(current_user.clerk_user_id)

    # Prevent duplicate escalations for the same conversation
    if _hitl_service.is_conversation_escalated(req.conversation_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This conversation is already escalated.",
        )

    ticket = _hitl_service.create_ticket(
        conversation_id=req.conversation_id,
        user_id=user_id,
        trigger_message_id=req.trigger_message_id,
        user_note=req.user_note,
    )

    logger.info(
        f"🎫 Escalation created | ticket={ticket.get('ticket_id')} | "
        f"user={user_id} | conv={req.conversation_id}"
    )

    return {
        "message": "Escalation ticket created successfully.",
        "ticket_id": ticket["ticket_id"],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAWYER QUEUE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/queue",
    summary="Get open ticket queue (lawyers and admins)",
)
async def get_ticket_queue(
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin")),
):
    """
    Phase 3: Lawyers see the shared queue of open (unassigned) tickets.

    Each ticket card includes:
    - User display_name, email, phone_number
    - conversation_summary (AI-generated, from conversations table)
    - created_at timestamp
    - status (always 'open' in this queue)
    """
    tickets = _hitl_service.get_open_tickets()
    return tickets


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SELF-ASSIGNMENT (Lawyer)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.patch(
    "/tickets/{ticket_id}/assign",
    summary="Lawyer self-assigns a ticket from the queue",
)
async def assign_ticket(
    ticket_id: str,
    background_tasks: BackgroundTasks,
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin")),
):
    """
    Phase 4: Lawyer clicks "Claim" on a ticket in the queue.

    Race-condition safe — if two lawyers click simultaneously, only the first
    one succeeds (DB-level .eq("status","open") guard). Returns 409 to the loser.

    After successful assignment:
    - Sends email to user notifying them their case has been accepted
    - User's chat UI can now poll for ticket status and show the booking flow
    """
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)

    success = _hitl_service.assign_ticket(ticket_id, lawyer_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This ticket was already claimed by another lawyer.",
        )

    # ── Notify user in the background ────────────────────────────────
    background_tasks.add_task(_send_assignment_notification, ticket_id, lawyer_id)

    logger.info(f"✅ Ticket claimed | ticket={ticket_id} | lawyer={lawyer_id}")
    return {"message": "Ticket assigned successfully.", "ticket_id": ticket_id}


async def _send_assignment_notification(ticket_id: str, lawyer_id: str):
    """Internal helper to send email without blocking the API response."""
    try:
        ticket = _hitl_service.get_ticket_by_id(ticket_id)
        if ticket and _email_service:
            user_email = ticket.get("user_email")
            user_name = ticket.get("user_display_name") or "User"

            # Get lawyer's display name
            lawyer_profile_resp = (
                _hitl_service._supabase.table("users")
                .select("user_profiles(display_name), user_name")
                .eq("user_id", lawyer_id)
                .limit(1)
                .execute()
            )
            lawyer_name = "Your assigned lawyer"
            if lawyer_profile_resp.data:
                ld = lawyer_profile_resp.data[0]
                lp = (ld.get("user_profiles") or {})
                lawyer_name = lp.get("display_name") or ld.get("user_name") or lawyer_name

            if user_email:
                await _email_service.send_lawyer_assigned_email(
                    to_email=user_email,
                    user_name=user_name,
                    lawyer_name=lawyer_name,
                    ticket_id=ticket_id,
                )
    except Exception as notify_exc:
        # Non-fatal — the assignment itself succeeded
        logger.warning(f"⚠️ User notification after assign failed (non-fatal) | {notify_exc}")

    return {"message": "Ticket assigned successfully.", "ticket_id": ticket_id}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TICKET DETAILS (Assigned Lawyer)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/tickets/{ticket_id}/details",
    summary="Get full ticket details including user profile and summary",
)
async def get_ticket_details(
    ticket_id: str,
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin")),
):
    """
    Phase 4: Assigned lawyer views the full case detail page.

    Returns user info, conversation summary (case brief), trigger message,
    booking status, and Google Meet link (once booking is confirmed).

    Access: Only the assigned lawyer or admin can call this.
    """
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)

    details = _hitl_service.get_ticket_with_user_details(ticket_id, lawyer_id)
    if not details:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized. You must be the assigned lawyer for this ticket.",
        )

    return details


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESPOND / RESOLVE (Lawyer)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "/tickets/{ticket_id}/respond",
    summary="Lawyer submits response and resolves the ticket",
)
async def respond_to_ticket(
    ticket_id: str,
    req: RespondRequest,
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin")),
):
    """
    Phase 8: Lawyer submits their final written response, optionally adding
    outcome notes for record-keeping.

    - content:       The written legal response sent to the user
    - outcome_notes: Optional internal notes (billing, case outcome, follow-up)

    Only the assigned lawyer can resolve their own ticket.
    Status transitions: assigned|booked → resolved
    """
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)

    # Verify assignment — lawyer must be assigned to this ticket
    details = _hitl_service.get_ticket_with_user_details(ticket_id, lawyer_id)
    if not details:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized. You must be the assigned lawyer for this ticket.",
        )

    success = _hitl_service.resolve_ticket_with_notes(
        ticket_id=ticket_id,
        lawyer_id=lawyer_id,
        content=req.content,
        outcome_notes=req.outcome_notes,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save response.",
        )

    logger.info(f"✅ Ticket resolved | ticket={ticket_id} | lawyer={lawyer_id}")
    return {"message": "Response submitted and ticket resolved.", "ticket_id": ticket_id}


@router.post(
    "/tickets/{ticket_id}/no-show",
    summary="Lawyer marks the user as a no-show",
)
async def mark_no_show(
    ticket_id: str,
    req: NoShowRequest = NoShowRequest(),
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin")),
):
    """
    Lawyer reporting that the user did not show up for the meeting.
    Status moves to 'no_show'.
    """
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    success = _hitl_service.mark_no_show(
        ticket_id, 
        notes=req.outcome_notes,
        no_show_type=req.no_show_type
    )
    if not success:
        raise HTTPException(status_code=400, detail="Ticket not found, not scheduled, or update failed.")
    
    return {"message": f"Case marked as {req.no_show_type} no-show. Rescheduling enabled."}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER TICKET STATUS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/my-tickets",
    summary="User views their own escalation tickets",
)
async def get_my_tickets(
    current_user: ClerkUser = Depends(require_db_role("user", "lawyer", "admin")),
):
    """
    User views all their own escalation tickets with current status.
    The frontend uses this to detect when a lawyer is assigned and trigger
    the Cal.com booking slot picker.

    Returns: ticket_id, status, booking_url, booking_confirmed_at, assigned_lawyer_id, created_at
    """
    user_id = _user_service.get_user_id_from_clerk_id(current_user.clerk_user_id)
    tickets = _hitl_service.get_user_tickets(user_id)
    return tickets


@router.get(
    "/my-active-tickets",
    summary="Lawyer views their own active (assigned/booked) tickets",
)
async def get_my_active_tickets(
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin")),
):
    """
    Lawyer views their own cases that are currently 'assigned' or 'booked'.
    Returns flattened data including user info and conversation summary.
    """
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    tickets = _hitl_service.get_lawyer_active_tickets(lawyer_id)
    return tickets


@router.get(
    "/my-resolved-tickets",
    summary="Lawyer views their resolved ticket history",
)
async def get_my_resolved_history(
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin")),
):
    """
    Lawyer views their full history of resolved/closed tickets.
    """
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    tickets = _hitl_service.get_lawyer_resolved_history(lawyer_id)
    return tickets


@router.get(
    "/status/{conversation_id}",
    summary="Check if a conversation is already escalated",
)
async def get_escalation_status(
    conversation_id: str,
    current_user: ClerkUser = Depends(require_db_role("user", "lawyer", "admin")),
):
    """
    Check if this conversation already has an active escalation ticket.
    Used by the chat UI to show the correct status and details.
    """
    ticket = _hitl_service.get_ticket_by_conversation(conversation_id)
    is_escalated = ticket is not None and ticket.get("status") in ["open", "assigned", "booked", "resolved"]
    
    return {
        "conversation_id": conversation_id, 
        "is_escalated": is_escalated,
        "ticket": ticket
    }