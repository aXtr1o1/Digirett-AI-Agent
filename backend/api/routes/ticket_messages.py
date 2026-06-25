"""
api/routes/ticket_messages.py — Pre-consultation ticket messaging thread endpoints

Endpoints:
  GET   /hitl/tickets/{ticket_id}/messages        — Fetch message thread (authorized only)
  POST  /hitl/tickets/{ticket_id}/messages        — Send a message and notify recipient (background task)
  PATCH /hitl/tickets/{ticket_id}/messages/read   — Mark messages sent by the other party as read
"""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks

from core.auth import ClerkUser, require_db_role
from services.email_service import EmailService
from services.hitl_service import HitlService
from services.user_service import UserService
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hitl/tickets", tags=["HITL Messaging"])

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
    logger.info("✅ ticket_messages router services set")


# ── Schemas ───────────────────────────────────────────────────────────

class MessageCreateRequest(BaseModel):
    content: str
    file_name: Optional[str] = None
    document_id: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _validate_ticket_access(ticket_id: str, current_user: ClerkUser) -> Dict[str, Any]:
    """
    Validates that the ticket exists and the current user is authorized to access it:
    - Users can only access their own tickets.
    - Lawyers can only access tickets they are assigned to.
    - Admins can access any ticket.
    """
    supabase = get_supabase()
    
    # Fetch ticket
    ticket_resp = supabase.table("hitl_tickets") \
        .select("ticket_id, user_id, assigned_lawyer_id, status") \
        .eq("ticket_id", ticket_id) \
        .execute()
        
    if not ticket_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found."
        )
        
    ticket = ticket_resp.data[0]
    user_role = current_user.db_role
    user_db_id = current_user.db_user_id
    
    # Robust fallback: if role/ID enrichment was skipped (e.g. temporary database blip),
    # query Supabase directly using the verified Clerk ID.
    if not user_db_id or not user_role:
        try:
            user_resp = supabase.table("users") \
                .select("user_id, role") \
                .eq("clerk_user_id", current_user.clerk_user_id) \
                .single() \
                .execute()
            if user_resp.data:
                user_db_id = user_resp.data.get("user_id")
                user_role = user_resp.data.get("role")
                # Write back to current_user to enrich it for downstream tasks
                current_user["db_user_id"] = user_db_id
                current_user["db_role"] = user_role
        except Exception as exc:
            logger.error(f"❌ Fallback user lookup failed in _validate_ticket_access | {exc}")
    
    if user_role in ("admin", "system_admin"):
        return ticket
        
    if user_role == "lawyer":
        if ticket.get("assigned_lawyer_id") != user_db_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized. You are not the assigned lawyer for this ticket."
            )
        return ticket
        
    # Default to user role check
    if ticket.get("user_id") != user_db_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized. You do not own this ticket."
        )
        
    return ticket


async def _send_message_notification_task(ticket_id: str, sender_id: str, sender_role: str, message_content: str):
    """
    Background task to fetch recipient and sender information, 
    then send an email notification.
    """
    if not _email_service:
        logger.warning("⚠️ Email service not set in ticket_messages router. Skipping notification.")
        return
        
    try:
        supabase = get_supabase()
        
        # 1. Fetch ticket details to get user_id and assigned_lawyer_id
        ticket_resp = supabase.table("hitl_tickets") \
            .select("user_id, assigned_lawyer_id") \
            .eq("ticket_id", ticket_id) \
            .single() \
            .execute()
            
        if not ticket_resp.data:
            return
            
        ticket = ticket_resp.data
        recipient_id = None
        
        # If user sent it, notify lawyer
        if sender_role == "user":
            recipient_id = ticket.get("assigned_lawyer_id")
        # If lawyer sent it, notify user
        elif sender_role == "lawyer":
            recipient_id = ticket.get("user_id")
            
        if not recipient_id:
            logger.debug("No recipient to notify (e.g., ticket is unassigned and user sent a message).")
            return
            
        # 2. Fetch recipient name & email
        recipient_resp = supabase.table("users") \
            .select("email, user_name, user_profiles(display_name)") \
            .eq("user_id", recipient_id) \
            .single() \
            .execute()
            
        # 3. Fetch sender name
        sender_resp = supabase.table("users") \
            .select("user_name, user_profiles(display_name)") \
            .eq("user_id", sender_id) \
            .single() \
            .execute()
            
        if recipient_resp.data and sender_resp.data:
            recip = recipient_resp.data
            send = sender_resp.data
            
            to_email = recip.get("email")
            if not to_email:
                return
                
            recipient_name = (recip.get("user_profiles") or {}).get("display_name") or recip.get("user_name") or "User"
            sender_name = (send.get("user_profiles") or {}).get("display_name") or send.get("user_name") or "User"
            
            # Add prefix/role clarification if needed
            if sender_role == "lawyer":
                sender_name = f"⚖️ {sender_name} (Your Lawyer)"
                
            await _email_service.send_ticket_message_notification(
                to_email=to_email,
                recipient_name=recipient_name,
                sender_name=sender_name,
                message_content=message_content,
                ticket_id=ticket_id
            )
            logger.info(f"📧 Pre-consultation message notification sent to {to_email}")
            
    except Exception as e:
        logger.warning(f"⚠️ Failed to send pre-consultation email notification (non-fatal): {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ROUTE HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/{ticket_id}/messages",
    summary="Get all messages in the pre-consultation thread",
)
def get_messages(
    ticket_id: str,
    current_user: ClerkUser = Depends(require_db_role("user", "lawyer", "admin")),
):
    """
    Fetches the pre-consultation message thread for a ticket.
    Accessible only by the ticket owner (user), assigned lawyer, or admins.
    """
    # Verify access permission
    _validate_ticket_access(ticket_id, current_user)
    
    supabase = get_supabase()
    
    try:
        resp = supabase.table("ticket_messages") \
            .select("*") \
            .eq("ticket_id", ticket_id) \
            .order("created_at", desc=False) \
            .execute()
            
        return resp.data or []
        
    except Exception as exc:
        logger.error(f"❌ Failed to fetch messages for ticket {ticket_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load message thread."
        )


@router.post(
    "/{ticket_id}/messages",
    summary="Send a message in the pre-consultation thread",
)
def send_message(
    ticket_id: str,
    req: MessageCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: ClerkUser = Depends(require_db_role("user", "lawyer", "admin")),
):
    """
    Sends a new message in the ticket's pre-consultation thread.
    Triggers a background task to send an email notification to the recipient.
    """
    # Verify access permission
    _validate_ticket_access(ticket_id, current_user)
    
    supabase = get_supabase()
    
    user_db_id = current_user.db_user_id
    user_role = current_user.db_role
    
    # Map database role to sender_role enum ('user' or 'lawyer')
    sender_role = "lawyer" if user_role in ("lawyer", "admin", "system_admin") else "user"
    
    try:
        message_data = {
            "ticket_id": ticket_id,
            "sender_id": user_db_id,
            "sender_role": sender_role,
            "content": req.content,
            "is_read": False
        }
        if req.file_name:
            message_data["file_name"] = req.file_name
        if req.document_id:
            message_data["document_id"] = req.document_id
        
        resp = supabase.table("ticket_messages").insert(message_data).execute()
        
        if not resp.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save message."
            )
            
        new_message = resp.data[0]
        
        # Trigger email notification in the background
        background_tasks.add_task(
            _send_message_notification_task,
            ticket_id=ticket_id,
            sender_id=user_db_id,
            sender_role=sender_role,
            message_content=req.content
        )
        
        return new_message
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"❌ Failed to send message for ticket {ticket_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message."
        )


@router.patch(
    "/{ticket_id}/messages/read",
    summary="Mark messages in the thread as read",
)
def mark_as_read(
    ticket_id: str,
    current_user: ClerkUser = Depends(require_db_role("user", "lawyer", "admin")),
):
    """
    Marks all unread messages sent by the opposite party in the thread as read.
    """
    # Verify access permission
    _validate_ticket_access(ticket_id, current_user)
    
    supabase = get_supabase()
    
    user_role = current_user.db_role
    
    # We want to mark messages sent by the OTHER party as read
    # If a user is calling this, mark lawyer messages as read.
    # If a lawyer/admin is calling this, mark user messages as read.
    opposite_role = "lawyer" if user_role not in ("lawyer", "admin", "system_admin") else "user"
    
    try:
        resp = supabase.table("ticket_messages") \
            .update({"is_read": True}) \
            .eq("ticket_id", ticket_id) \
            .eq("sender_role", opposite_role) \
            .eq("is_read", False) \
            .execute()
            
        return {"status": "success", "count": len(resp.data or [])}
        
    except Exception as exc:
        logger.error(f"❌ Failed to mark messages as read for ticket {ticket_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update read status."
        )
