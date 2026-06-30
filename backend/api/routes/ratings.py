import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from config import settings

from core.auth import ClerkUser, require_db_role, get_current_user
from db.supabase_client import get_supabase
from services.email_service import EmailService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ratings", tags=["Ratings"])

_email_service: Optional[EmailService] = None

def set_services(email_svc: Optional[EmailService] = None) -> None:
    global _email_service
    _email_service = email_svc

class RatingSubmitRequest(BaseModel):
    ticket_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

@router.post("", summary="Submit consultation feedback and rating")
async def submit_rating(
    req: RatingSubmitRequest,
    background_tasks: BackgroundTasks,
    current_user: ClerkUser = Depends(get_current_user),
):
    supabase = get_supabase()
    
    # 1. Fetch ticket to verify ownership and get assigned lawyer
    ticket_query = supabase.table("hitl_tickets") \
        .select("ticket_id, user_id, status, assigned_lawyer_id") \
        .eq("ticket_id", req.ticket_id)
    ticket_resp = supabase.execute_query(ticket_query)
        
    if not ticket_resp.data:
        raise HTTPException(status_code=404, detail="Ticket not found.")
        
    ticket = ticket_resp.data[0]
    
    # 2. Get internal performer user ID
    performer_query = supabase.table("users") \
        .select("user_id") \
        .eq("clerk_user_id", current_user.clerk_user_id) \
        .single()
    performer_resp = supabase.execute_query(performer_query)
        
    if not performer_resp.data:
        raise HTTPException(status_code=404, detail="User profile not found.")
        
    internal_user_id = performer_resp.data["user_id"]
    
    # Verify user owns this ticket
    if ticket.get("user_id") != internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only rate your own tickets."
        )
        
    # Verify ticket state
    if ticket.get("status") not in ["resolved", "closed"]:
        raise HTTPException(
            status_code=400,
            detail="You can only rate tickets that are resolved or closed."
        )
        
    lawyer_id = ticket.get("assigned_lawyer_id")
    if not lawyer_id:
        raise HTTPException(
            status_code=400,
            detail="This ticket does not have an assigned lawyer to rate."
        )
        
    # 3. Insert rating
    try:
        insert_query = supabase.table("consultation_ratings").upsert({
            "ticket_id": req.ticket_id,
            "user_id": internal_user_id,
            "lawyer_id": lawyer_id,
            "rating": req.rating,
            "comment": req.comment
        }, on_conflict="ticket_id")
        supabase.execute_query(insert_query)
        
        # 4. Trigger background email notification
        if _email_service:
            background_tasks.add_task(
                _send_rating_notification,
                ticket_id=req.ticket_id,
                lawyer_id=lawyer_id,
                rating=req.rating,
                comment=req.comment
            )
        
        return {"status": "success", "message": "Feedback submitted successfully."}
    except Exception as exc:
        logger.error(f"Failed to submit rating: {exc}")
        raise HTTPException(status_code=500, detail="Failed to store feedback.")


async def _send_rating_notification(
    ticket_id: str,
    lawyer_id: str,
    rating: int,
    comment: Optional[str] = None
):
    """Internal helper to notify lawyer of new rating and copy admin if low rating."""
    try:
        supabase = get_supabase()
        
        # Get lawyer profile
        lawyer_query = supabase.table("users") \
            .select("email, user_name, user_profiles(display_name)") \
            .eq("user_id", lawyer_id) \
            .single()
        lawyer_resp = supabase.execute_query(lawyer_query)
            
        if lawyer_resp.data and _email_service:
            lawyer_data = lawyer_resp.data
            to_email = lawyer_data.get("email")
            
            profile = lawyer_data.get("user_profiles") or {}
            lawyer_name = profile.get("display_name") or lawyer_data.get("user_name") or "Lawyer"
            
            if to_email:
                await _email_service.send_consultation_feedback_email(
                    to_email=to_email,
                    lawyer_name=lawyer_name,
                    ticket_id=ticket_id,
                    rating=rating,
                    comment=comment
                )
                
            # If low rating (<= 2 stars), notify admin for Quality Assurance
            admin_email = settings.ADMIN_ALERT_EMAIL
            if rating <= 2 and admin_email:
                await _email_service.send_consultation_feedback_email(
                    to_email=admin_email,
                    lawyer_name=f"{lawyer_name} (Admin Review)",
                    ticket_id=ticket_id,
                    rating=rating,
                    comment=f"[QA REVIEW REQUIRED] {comment or 'No comment provided.'}"
                )
    except Exception as exc:
        logger.warning(f"⚠️ Failed to send rating notification email (non-fatal) | {exc}")


@router.get("/lawyer", summary="Get rating logs for the logged-in lawyer")
async def get_lawyer_ratings(
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer")),
):
    supabase = get_supabase()
    
    # Get internal user ID of lawyer
    performer_query = supabase.table("users") \
        .select("user_id") \
        .eq("clerk_user_id", current_lawyer.clerk_user_id) \
        .single()
    performer_resp = supabase.execute_query(performer_query)
        
    if not performer_resp.data:
        raise HTTPException(status_code=404, detail="Lawyer profile not found.")
        
    lawyer_id = performer_resp.data["user_id"]
    
    ratings_query = supabase.table("consultation_ratings") \
        .select("rating_id, rating, comment, created_at, ticket_id") \
        .eq("lawyer_id", lawyer_id)
    resp = supabase.execute_query(ratings_query)
        
    return resp.data or []

@router.get("/admin", summary="Get all ratings in the system for admin audit")
async def get_admin_ratings(
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
):
    supabase = get_supabase()
    ratings_query = supabase.table("consultation_ratings") \
        .select("*, users!consultation_ratings_lawyer_id_fkey(user_name, email)") \
        .order("created_at", desc=True)
    resp = supabase.execute_query(ratings_query)
    return resp.data or []
