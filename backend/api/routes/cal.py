"""
api/routes/cal.py — Cal.com slot fetching & booking creation

Endpoints:
  GET  /cal/slots/{ticket_id}          — User fetches available slots for assigned lawyer
  POST /cal/bookings/{ticket_id}       — User creates a booking for a specific slot

Security:
  - Slots: accessible by the ticket owner (user) OR the assigned lawyer OR admin
  - Bookings: accessible only by the ticket owner (user)

Flow:
  1. Lawyer is assigned to ticket (hitl_service.assign_ticket)
  2. Frontend polls GET /cal/slots/{ticket_id} to show available times
  3. User picks a slot → POST /cal/bookings/{ticket_id} with start_time
  4. Backend creates Cal.com booking with user details + metadata (ticketId, conversationId)
  5. Cal.com fires webhook → cal_webhooks.py updates ticket status to "booked" + stores Meet link
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core.auth import ClerkUser, require_db_role
from services.cal_service import CalService
from services.hitl_service import HitlService
from services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cal", tags=["Cal.com Booking"])

# ── Services ─────────────────────────────────────────────────────────
_cal_service: Optional[CalService] = None
_hitl_service: Optional[HitlService] = None
_user_service: Optional[UserService] = None


def set_services(
    cal_svc: CalService,
    hitl_svc: HitlService,
    user_svc: UserService,
) -> None:
    global _cal_service, _hitl_service, _user_service
    _cal_service = cal_svc
    _hitl_service = hitl_svc
    _user_service = user_svc


# ── Schemas ──────────────────────────────────────────────────────────

class BookingRequest(BaseModel):
    """Body for POST /cal/bookings/{ticket_id}"""
    start_time: str    # ISO 8601 slot datetime chosen by user e.g. "2026-05-15T09:00:00Z"
    timezone: str = "Europe/Oslo"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Internal helper — fetch ticket + verify credentials exist
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_lawyer_cal_credentials(ticket: Dict[str, Any]):
    """
    From a ticket dict, look up the assigned lawyer's Cal.com credentials
    stored in lawyer_profiles (cal_api_key, cal_event_type_id).

    Returns (api_key, event_type_id) or raises HTTPException.
    """
    lawyer_id = ticket.get("assigned_lawyer_id")
    if not lawyer_id:
        logger.warning(f"⚠️ Cal.com credentials lookup failed: No lawyer assigned to ticket {ticket.get('ticket_id')}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No lawyer assigned to this ticket yet.",
        )

    # Fetch lawyer profile for Cal.com credentials
    from db.supabase_client import get_supabase
    supabase = get_supabase()
    resp = (
        supabase.table("lawyer_profiles")
        .select("cal_api_key, cal_event_type_id")
        .eq("lawyer_id", lawyer_id)
        .limit(1)
        .execute()
    )

    if not resp.data:
        logger.error(f"❌ Cal.com credentials lookup failed: No profile found in lawyer_profiles for lawyer_id {lawyer_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found. Please ensure the lawyer has configured their Cal.com settings.",
        )

    profile = resp.data[0]
    api_key = profile.get("cal_api_key")
    event_type_id = profile.get("cal_event_type_id")

    if not api_key or not event_type_id:
        logger.error(f"❌ Cal.com credentials lookup failed: Profile found for {lawyer_id} but api_key or event_type_id is missing")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lawyer has not fully configured their Cal.com credentials.",
        )

    logger.info(f"✅ Cal.com credentials found for lawyer {lawyer_id}")
    return api_key, int(event_type_id)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ROUTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/slots/{ticket_id}",
    summary="Fetch available Cal.com slots for the assigned lawyer",
)
async def get_lawyer_slots(
    ticket_id: str,
    start_date: Optional[str] = None,  # YYYY-MM-DD, defaults to today
    end_date: Optional[str] = None,    # YYYY-MM-DD, defaults to today+7
    timezone: str = "Europe/Oslo",
    current_user: ClerkUser = Depends(require_db_role("user", "lawyer", "admin")),
):
    """
    Fetches available booking slots for the lawyer assigned to this ticket.

    Use Case (Phase 6):
      After a lawyer is assigned, the chat UI shows a slot picker.
      The frontend calls this endpoint to get available times.

    Access:
      - The ticket's user, the assigned lawyer, or any admin can call this.
    
    Returns:
      Cal.com slots response with date-keyed arrays of available times.
    """
    # Fetch the ticket
    ticket = _hitl_service.get_ticket_by_id(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    # Auth check: only ticket owner, assigned lawyer, or admin
    caller_user_id = _user_service.get_user_id_from_clerk_id(current_user.clerk_user_id)
    is_ticket_owner = ticket.get("user_id") == caller_user_id
    is_assigned_lawyer = ticket.get("assigned_lawyer_id") == caller_user_id
    is_admin = current_user.role == "admin"  # JWT role check for speed; DB role already verified

    if not (is_ticket_owner or is_assigned_lawyer or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view slots for this ticket.",
        )

    # Ticket must be in 'assigned' status before booking is relevant
    if ticket.get("status") not in ("assigned", "booked"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Booking slots are only available once a lawyer is assigned. Current status: {ticket.get('status')}",
        )

    # Get Cal.com credentials from lawyer_profiles
    api_key, event_type_id = _get_lawyer_cal_credentials(ticket)

    # Fetch slots
    try:
        slots = await _cal_service.get_available_slots(
            cal_api_key=api_key,
            event_type_id=event_type_id,
            start_date=start_date,
            end_date=end_date,
            timezone=timezone,
        )
    except ValueError as exc:
        logger.warning(f"⚠️ CalService error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return {
        "ticket_id": ticket_id,
        "lawyer_id": ticket.get("assigned_lawyer_id"),
        "slots": slots.get("slots", {}),
    }


@router.post(
    "/bookings/{ticket_id}",
    summary="Book a slot on the assigned lawyer's calendar",
)
async def create_booking(
    ticket_id: str,
    req: BookingRequest,
    current_user: ClerkUser = Depends(require_db_role("user", "admin")),
):
    """
    Books a specific slot for the user with the assigned lawyer.

    Use Case (Phase 6):
      After the user picks a slot from the slot picker, this endpoint
      creates the actual Cal.com booking and attaches our metadata
      (ticketId, conversationId) so the Cal.com webhook can link the
      booking back to this ticket when it fires.

    Access:
      - Only the ticket's user or admin can create a booking.
      - Ticket must be in 'assigned' status.

    Returns:
      Booking confirmation from Cal.com (without sensitive API keys).
      The Google Meet link arrives later via Cal.com webhook.
    """
    # Fetch ticket
    ticket = _hitl_service.get_ticket_by_id(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    # Auth: only the ticket owner or admin
    caller_user_id = _user_service.get_user_id_from_clerk_id(current_user.clerk_user_id)
    is_ticket_owner = ticket.get("user_id") == caller_user_id

    if not is_ticket_owner and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the ticket owner can create a booking.",
        )

    # Must be assigned
    if ticket.get("status") != "assigned":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot book: ticket status is '{ticket.get('status')}'. Must be 'assigned'.",
        )

    # Prevent double-booking
    if ticket.get("booking_cal_booking_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A booking already exists for this ticket.",
        )

    # Get Cal.com credentials
    api_key, event_type_id = _get_lawyer_cal_credentials(ticket)

    # Get user details for the booking
    from db.supabase_client import get_supabase
    supabase = get_supabase()
    user_resp = (
        supabase.table("users")
        .select("email, user_name, user_profiles(display_name)")
        .eq("user_id", ticket["user_id"])
        .limit(1)
        .execute()
    )

    user_data = user_resp.data[0] if user_resp.data else {}
    profile = (user_data.get("user_profiles") or {})
    user_name = profile.get("display_name") or user_data.get("user_name") or "User"
    user_email = user_data.get("email") or ""

    # Create booking
    booking_result = await _cal_service.create_booking(
        cal_api_key=api_key,
        event_type_id=event_type_id,
        start_time=req.start_time,
        user_name=user_name,
        user_email=user_email,
        conversation_id=ticket.get("conversation_id", ""),
        ticket_id=ticket_id,
        timezone=req.timezone,
    )

    # ✅ Update ticket status IMMEDIATELY so UI updates without waiting for webhook
    meet_link = _cal_service.extract_meet_link(booking_result)
    _hitl_service.update_booking(
        ticket_id=ticket_id,
        cal_booking_id=str(booking_result.get("id") or ""),
        booking_url=meet_link,
        meeting_time=req.start_time
    )

    logger.info(
        f"✅ Booking created | ticket={ticket_id} | cal_id={booking_result.get('id')} | "
        f"start={req.start_time}"
    )

    # Return safe subset (no API keys)
    return {
        "ticket_id": ticket_id,
        "cal_booking_id": booking_result.get("id"),
        "uid": booking_result.get("uid"),
        "start_time": booking_result.get("startTime"),
        "end_time": booking_result.get("endTime"),
        "status": booking_result.get("status"),
        "message": "Booking created. You will receive a confirmation email with the Google Meet link shortly.",
    }
