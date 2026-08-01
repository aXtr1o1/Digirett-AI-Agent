"""
api/routes/cal_webhooks.py — Cal.com booking confirmation webhook

Refactored according to TL code review guidelines:
- Pure FastAPI Dependency Injection via Request.app.state
- Top-level module-scope import of CalService
- Idempotency & Replay Protection against duplicate webhook deliveries
- Delegated user & lawyer notification orchestration to HitlService
- Consistent background task execution for confirmation and cancellation emails
- Pydantic CalWebhookResponse schema for OpenAPI/Swagger contract definitions
"""

import hashlib
import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status, BackgroundTasks

from pydantic import BaseModel

from config import settings
from services.cal_service import CalService
from services.email_service import EmailService
from services.hitl_service import HitlService

logger = logging.getLogger(__name__)

router = APIRouter()


def get_hitl_service(request: Request) -> HitlService:
    svc = getattr(request.app.state, "hitl_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HitlService is not initialized on application state.",
        )
    return svc


def get_email_service(request: Request) -> Optional[EmailService]:
    return getattr(request.app.state, "email_service", None)


# ── Schemas ──────────────────────────────────────────────────────────

class CalWebhookResponse(BaseModel):
    status: str
    ticket_id: Optional[str] = None
    cal_booking_id: Optional[str] = None
    booking_url: Optional[str] = None
    action: Optional[str] = None
    reason: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Signature verification
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _verify_cal_signature(payload: bytes, signature_header: Optional[str]) -> bool:
    """
    Verify Cal.com webhook HMAC-SHA256 signature.
    Header format: X-Cal-Signature-256: sha256=<hex_digest>
    """
    secret = settings.CAL_COM_WEBHOOK_SECRET
    if not secret:
        logger.warning("⚠️ CAL_COM_WEBHOOK_SECRET not set — skipping webhook signature verification")
        return True

    if not signature_header:
        return False

    expected_sig = signature_header.replace("sha256=", "")
    computed = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, expected_sig)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Webhook endpoint
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "/cal",
    tags=["Webhooks"],
    summary="Handle Cal.com booking events",
    response_model=CalWebhookResponse,
)
async def cal_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_cal_signature_256: Optional[str] = Header(None, alias="X-Cal-Signature-256"),
    hitl_service: HitlService = Depends(get_hitl_service),
    email_service: Optional[EmailService] = Depends(get_email_service),
):
    """
    Receives Cal.com webhook events (BOOKING_CREATED, BOOKING_CONFIRMED, BOOKING_CANCELLED, etc.)
    """
    payload = await request.body()

    if not _verify_cal_signature(payload, x_cal_signature_256):
        logger.warning("⚠️ Cal.com webhook signature mismatch — rejecting")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    trigger_event = data.get("triggerEvent") or data.get("type", "")
    logger.info(f"📩 Cal.com webhook received | event={trigger_event}")

    is_booking_event = trigger_event in ("BOOKING_CREATED", "BOOKING_CONFIRMED", "booking.created", "booking.confirmed")
    is_reschedule_event = trigger_event in ("BOOKING_RESCHEDULED", "booking.rescheduled")
    is_cancelled_event = trigger_event in ("BOOKING_CANCELLED", "booking.cancelled")

    if not (is_booking_event or is_reschedule_event or is_cancelled_event):
        logger.info(f"ℹ️ Cal.com webhook ignored | event={trigger_event}")
        return CalWebhookResponse(status="ignored", reason=f"Unhandled event: {trigger_event}")

    booking = data.get("payload") or data
    cal_booking_id = str(booking.get("id") or booking.get("uid") or "")
    if not cal_booking_id:
        logger.error("❌ Cal.com webhook: no booking ID found in payload")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No booking ID in payload")

    metadata = booking.get("metadata") or {}
    ticket_id = metadata.get("ticketId")
    if not ticket_id:
        logger.warning(f"⚠️ Cal.com booking {cal_booking_id} has no ticketId metadata")
        return CalWebhookResponse(status="ignored", reason="No ticketId in booking metadata")

    # Idempotency check: Skip duplicate updates/emails if already processed
    if hitl_service.is_cal_webhook_processed(ticket_id=ticket_id, cal_booking_id=cal_booking_id, is_cancelled=is_cancelled_event):
        logger.info(f"🔁 Cal.com webhook duplicate event skipped | ticket={ticket_id} | cal_id={cal_booking_id}")
        return CalWebhookResponse(
            status="already_processed",
            ticket_id=ticket_id,
            cal_booking_id=cal_booking_id,
            reason="Webhook event already processed for this ticket",
        )

    # Extract Meet link using module-scoped CalService
    meet_link = CalService.extract_meet_link(booking) or booking.get("videoCallUrl") or booking.get("video_call_url")

    # Handle Cancellation
    if is_cancelled_event:
        hitl_service.handle_cancellation(ticket_id)
        logger.info(f"🗑️ Booking cancelled for ticket {ticket_id}. Status reset to 'assigned'.")
        if email_service:
            background_tasks.add_task(
                hitl_service.send_booking_cancellation_notifications,
                ticket_id=ticket_id,
                email_service=email_service,
            )
        return CalWebhookResponse(status="success", action="ticket_reset", ticket_id=ticket_id)

    # Handle Booking / Reschedule
    start_time = str(booking.get("startTime") or booking.get("start_time") or "")
    success = hitl_service.update_booking(
        ticket_id=ticket_id,
        cal_booking_id=cal_booking_id,
        booking_url=meet_link,
        meeting_time=start_time,
    )

    if not success:
        logger.error(f"❌ Failed to update booking on ticket {ticket_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update booking record")

    logger.info(f"✅ Cal.com booking {trigger_event} | ticket={ticket_id} | cal_id={cal_booking_id} | meet={meet_link}")

    # Offload booking confirmation notifications to BackgroundTasks (non-blocking)
    if email_service:
        background_tasks.add_task(
            hitl_service.send_booking_confirmation_notifications,
            ticket_id=ticket_id,
            meet_link=meet_link,
            start_time=start_time,
            email_service=email_service,
        )

    return CalWebhookResponse(
        status="success",
        ticket_id=ticket_id,
        cal_booking_id=cal_booking_id,
        booking_url=meet_link,
    )