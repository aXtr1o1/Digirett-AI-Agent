import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from core.auth import ClerkUser, require_db_role
from schemas.enums import TicketStatus
from schemas.requests import BookingRequest, CalConfigUpdateRequest
from schemas.responses import (
    CalBookingResponse,
    CalLawyerConfigResponse,
    CalMessageResponse,
    CalSlotsResponse,
)
from services.cal_service import CalService
from services.hitl_service import HitlService
from services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cal", tags=["Cal.com Booking"])

_hitl_service: Optional[HitlService] = None
_user_service: Optional[UserService] = None


def set_services(hitl_svc: HitlService, user_svc: Optional[UserService] = None) -> None:
    """Legacy service injector for testing / backwards compatibility."""
    global _hitl_service, _user_service
    _hitl_service = hitl_svc
    _user_service = user_svc


def get_cal_service(request: Request) -> CalService:
    svc = getattr(request.app.state, "cal_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CalService is not initialized on application state.",
        )
    return svc


def get_hitl_service(request: Request) -> HitlService:
    svc = getattr(request.app.state, "hitl_service", None) or _hitl_service
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HitlService is not initialized on application state.",
        )
    return svc


def get_user_service(request: Request) -> UserService:
    svc = getattr(request.app.state, "user_service", None) or _user_service
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UserService is not initialized on application state.",
        )
    return svc


def _resolve_lawyer_credentials(ticket: Dict[str, Any], user_service: UserService) -> Tuple[str, int]:
    """Resolves and validates Cal.com credentials using UserService."""
    lawyer_id = ticket.get("assigned_lawyer_id")
    if not lawyer_id:
        logger.warning(f" Cal.com credentials lookup failed: No lawyer assigned to ticket {ticket.get('ticket_id')}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No lawyer assigned to this ticket yet.",
        )

    profile = user_service.get_lawyer_cal_credentials(lawyer_id)
    if not profile:
        logger.error(f" Cal.com credentials lookup failed: No profile found for lawyer_id {lawyer_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found. Please ensure the lawyer has configured their Cal.com settings.",
        )

    api_key = profile.get("cal_api_key")
    event_type_id = profile.get("cal_event_type_id")

    if not api_key or not event_type_id:
        logger.error(f" Cal.com credentials lookup failed: Profile found for {lawyer_id} but missing api_key or event_type_id")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lawyer has not fully configured their Cal.com credentials.",
        )

    return api_key, int(event_type_id)


def _authorize_ticket_access(
    ticket: Dict[str, Any],
    caller_user_id: Optional[str],
    current_user_role: str,
    require_owner_only: bool = False,
) -> None:
    """Verifies that caller is authorized to view or perform actions on a ticket."""
    is_ticket_owner = ticket.get("user_id") == caller_user_id
    is_assigned_lawyer = ticket.get("assigned_lawyer_id") == caller_user_id
    is_admin = current_user_role == "admin"

    if require_owner_only:
        if not (is_ticket_owner or is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the ticket owner or admin can perform this action.",
            )
    else:
        if not (is_ticket_owner or is_assigned_lawyer or is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access slots for this ticket.",
            )

@router.get(
    "/slots/{ticket_id}",
    summary="Fetch available Cal.com slots for the assigned lawyer",
    response_model=CalSlotsResponse,
)
async def get_lawyer_slots(
    ticket_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timezone: str = "Europe/Oslo",
    current_user: ClerkUser = Depends(require_db_role("user", "lawyer", "admin")),
    cal_service: CalService = Depends(get_cal_service),
    hitl_service: HitlService = Depends(get_hitl_service),
    user_service: UserService = Depends(get_user_service),
):
    """Fetches available booking slots for the lawyer assigned to this ticket."""
    ticket = hitl_service.get_ticket_by_id(ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    caller_user_id = user_service.get_user_id_from_clerk_id(current_user.clerk_user_id)
    _authorize_ticket_access(ticket, caller_user_id, current_user.role, require_owner_only=False)

    ticket_status = ticket.get("status")
    if ticket_status not in (TicketStatus.ASSIGNED.value, TicketStatus.BOOKED.value, "assigned", "booked"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Booking slots are only available once a lawyer is assigned. Current status: {ticket_status}",
        )

    api_key, event_type_id = _resolve_lawyer_credentials(ticket, user_service)

    try:
        slots = await cal_service.get_available_slots(
            cal_api_key=api_key,
            event_type_id=event_type_id,
            start_date=start_date,
            end_date=end_date,
            timezone=timezone,
        )
    except ValueError as exc:
        logger.warning(f" CalService error: {exc}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return CalSlotsResponse(
        ticket_id=ticket_id,
        lawyer_id=ticket.get("assigned_lawyer_id"),
        slots=slots.slots if hasattr(slots, "slots") else (slots.get("slots", {}) if isinstance(slots, dict) else {}),
    )


@router.post(
    "/bookings/{ticket_id}",
    summary="Book a slot on the assigned lawyer's calendar",
    response_model=CalBookingResponse,
)
async def create_booking(
    ticket_id: str,
    req: BookingRequest,
    current_user: ClerkUser = Depends(require_db_role("user", "admin")),
    cal_service: CalService = Depends(get_cal_service),
    hitl_service: HitlService = Depends(get_hitl_service),
    user_service: UserService = Depends(get_user_service),
):
    """Books a specific slot for the user with the assigned lawyer."""
    ticket = hitl_service.get_ticket_by_id(ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    caller_user_id = user_service.get_user_id_from_clerk_id(current_user.clerk_user_id)
    _authorize_ticket_access(ticket, caller_user_id, current_user.role, require_owner_only=True)

    ticket_status = ticket.get("status")
    if ticket_status not in (TicketStatus.ASSIGNED.value, "assigned"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot book: ticket status is '{ticket_status}'. Must be '{TicketStatus.ASSIGNED.value}'.",
        )

    if ticket.get("booking_cal_booking_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A booking already exists for this ticket.",
        )

    api_key, event_type_id = _resolve_lawyer_credentials(ticket, user_service)
    user_info = user_service.get_user_profile_for_booking(ticket["user_id"])

    booking_result = await cal_service.create_booking(
        cal_api_key=api_key,
        event_type_id=event_type_id,
        start_time=req.start_time,
        user_name=user_info.get("user_name", "User"),
        user_email=user_info.get("email", ""),
        conversation_id=ticket.get("conversation_id", ""),
        ticket_id=ticket_id,
        timezone=req.timezone,
    )

    meet_link = cal_service.extract_meet_link(booking_result)
    cal_booking_id = str(booking_result.id or "")
    hitl_service.update_booking(
        ticket_id=ticket_id,
        cal_booking_id=cal_booking_id,
        booking_url=meet_link,
        meeting_time=req.start_time,
    )

    logger.info(f" Booking created | ticket={ticket_id} | cal_id={booking_result.id} | start={req.start_time}")

    raw_data = booking_result.raw_data or {}

    return CalBookingResponse(
        ticket_id=ticket_id,
        cal_booking_id=booking_result.id,
        uid=booking_result.uid,
        start_time=raw_data.get("start") or raw_data.get("startTime") or req.start_time,
        end_time=raw_data.get("end") or raw_data.get("endTime"),
        status=booking_result.status,
        message="Booking created. You will receive a confirmation email with the Google Meet link shortly.",
    )


@router.get(
    "/lawyer/config",
    summary="Get the current lawyer's Cal.com configuration",
    response_model=CalLawyerConfigResponse,
)
async def get_lawyer_cal_config(
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin")),
    user_service: UserService = Depends(get_user_service),
):
    lawyer_id = user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    if not lawyer_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    config = user_service.get_lawyer_cal_config(lawyer_id)
    if not config:
        return CalLawyerConfigResponse(cal_event_type_id="", cal_api_key="")

    return CalLawyerConfigResponse(
        cal_event_type_id=str(config.get("cal_event_type_id", "")),
        cal_api_key=str(config.get("cal_api_key", "")),
    )


@router.put(
    "/lawyer/config",
    summary="Update the current lawyer's Cal.com configuration",
    response_model=CalMessageResponse,
)
async def update_lawyer_cal_config(
    req: CalConfigUpdateRequest,
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin")),
    user_service: UserService = Depends(get_user_service),
):
    lawyer_id = user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    if not lawyer_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    success = user_service.update_lawyer_cal_config(
        lawyer_id,
        event_type_id=req.cal_event_type_id,
        api_key=req.cal_api_key,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update configuration",
        )

    return CalMessageResponse(message="Configuration updated successfully")