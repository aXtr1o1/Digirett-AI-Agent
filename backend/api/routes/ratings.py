import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.auth import ClerkUser, require_db_role, get_current_user
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ratings", tags=["Ratings"])

class RatingSubmitRequest(BaseModel):
    ticket_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

@router.post("", summary="Submit consultation feedback and rating")
async def submit_rating(
    req: RatingSubmitRequest,
    current_user: ClerkUser = Depends(get_current_user),
):
    supabase = get_supabase()
    
    # 1. Fetch ticket to verify ownership and get assigned lawyer
    ticket_resp = supabase.table("hitl_tickets") \
        .select("ticket_id, user_id, status, assigned_lawyer_id") \
        .eq("ticket_id", req.ticket_id) \
        .execute()
        
    if not ticket_resp.data:
        raise HTTPException(status_code=404, detail="Ticket not found.")
        
    ticket = ticket_resp.data[0]
    
    # 2. Get internal performer user ID
    performer_resp = supabase.table("users") \
        .select("user_id") \
        .eq("clerk_user_id", current_user.clerk_user_id) \
        .single() \
        .execute()
        
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
        supabase.table("consultation_ratings").upsert({
            "ticket_id": req.ticket_id,
            "user_id": internal_user_id,
            "lawyer_id": lawyer_id,
            "rating": req.rating,
            "comment": req.comment
        }, on_conflict="ticket_id").execute()
        
        return {"status": "success", "message": "Feedback submitted successfully."}
    except Exception as exc:
        logger.error(f"Failed to submit rating: {exc}")
        raise HTTPException(status_code=500, detail="Failed to store feedback.")

@router.get("/lawyer", summary="Get rating logs for the logged-in lawyer")
async def get_lawyer_ratings(
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer")),
):
    supabase = get_supabase()
    
    # Get internal user ID of lawyer
    performer_resp = supabase.table("users") \
        .select("user_id") \
        .eq("clerk_user_id", current_lawyer.clerk_user_id) \
        .single() \
        .execute()
        
    if not performer_resp.data:
        raise HTTPException(status_code=404, detail="Lawyer profile not found.")
        
    lawyer_id = performer_resp.data["user_id"]
    
    resp = supabase.table("consultation_ratings") \
        .select("rating_id, rating, comment, created_at, ticket_id") \
        .eq("lawyer_id", lawyer_id) \
        .execute()
        
    return resp.data or []

@router.get("/admin", summary="Get all ratings in the system for admin audit")
async def get_admin_ratings(
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
):
    supabase = get_supabase()
    resp = supabase.table("consultation_ratings") \
        .select("*, users!consultation_ratings_lawyer_id_fkey(user_name, email)") \
        .order("created_at", desc=True) \
        .execute()
    return resp.data or []
