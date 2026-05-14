"""
api/routes/cal_webhooks.py — Cal.com booking confirmation webhook

Cal.com fires a POST to this endpoint when a booking is confirmed.
We extract:
  - The booking ID
  - The Google Meet link (from references[].meetingUrl)
  - The ticketId stored in booking metadata (set during create_booking)

Then we update the hitl_ticket record:
  - booking_cal_booking_id  = Cal.com booking ID
  - booking_url             = Google Meet link
  - booking_confirmed_at    = now
  - status                  = "booked"

Security: Cal.com signs webhooks with HMAC-SHA256 using a shared secret.
We verify the X-Cal-Signature-256 header before processing.

NOTE: Add your CAL_COM_WEBHOOK_SECRET to .env (from Cal.com dashboard → Webhooks).
"""

import hashlib
import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, status

from config import settings
from services.hitl_service import HitlService
from services.email_service import EmailService

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Services ─────────────────────────────────────────────────────────
_hitl_service: Optional[HitlService] = None
_email_service: Optional[EmailService] = None


def set_services(hitl_svc: HitlService, email_svc: EmailService) -> None:
    global _hitl_service, _email_service
    _hitl_service = hitl_svc
    _email_service = email_svc


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Signature verification
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _verify_cal_signature(payload: bytes, signature_header: Optional[str]) -> bool:
    """
    Verify Cal.com webhook HMAC-SHA256 signature.
    Header format: X-Cal-Signature-256: sha256=<hex_digest>

    If CAL_COM_WEBHOOK_SECRET is not configured, we skip verification
    (useful for local development) but log a warning.
    """
    secret = settings.CAL_COM_WEBHOOK_SECRET
    if not secret:
        logger.warning("⚠️ CAL_COM_WEBHOOK_SECRET not set — skipping webhook signature verification")
        return True

    if not signature_header:
        return False

    # Strip "sha256=" prefix if present
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
)
async def cal_webhook(
    request: Request,
    x_cal_signature_256: Optional[str] = Header(None, alias="X-Cal-Signature-256"),
):
    """
    Receives Cal.com webhook events (BOOKING_CREATED, BOOKING_CONFIRMED, etc.)

    On BOOKING_CREATED / BOOKING_CONFIRMED:
      1. Extracts ticketId from booking.metadata
      2. Extracts Google Meet link from booking.references
      3. Updates hitl_ticket: status=booked, booking_url, booking_cal_booking_id,
         booking_confirmed_at
      4. Sends confirmation email to user with the Google Meet link

    Cal.com sends the webhook body as JSON. The relevant event types are:
      - BOOKING_CREATED      → fire immediately on new booking
      - BOOKING_CONFIRMED    → fire after confirmation (if requires_confirmation=true)
    """
    payload = await request.body()

    # Verify signature
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

    # Only handle booking creation/confirmation events
    if trigger_event not in ("BOOKING_CREATED", "BOOKING_CONFIRMED", "booking.created", "booking.confirmed"):
        logger.info(f"ℹ️ Cal.com webhook ignored | event={trigger_event}")
        return {"status": "ignored", "reason": f"Unhandled event: {trigger_event}"}

    # ── Extract booking payload ──────────────────────────────────────
    # Cal.com wraps everything in `payload` key for newer webhook versions
    booking = data.get("payload") or data

    cal_booking_id = str(booking.get("id") or booking.get("uid") or "")
    if not cal_booking_id:
        logger.error("❌ Cal.com webhook: no booking ID found in payload")
        raise HTTPException(status_code=400, detail="No booking ID in payload")

    # ── Extract our ticketId from metadata ───────────────────────────
    metadata = booking.get("metadata") or {}
    ticket_id = metadata.get("ticketId")
    if not ticket_id:
        logger.warning(f"⚠️ Cal.com booking {cal_booking_id} has no ticketId metadata — cannot link to HITL ticket")
        return {"status": "ignored", "reason": "No ticketId in booking metadata", "extracted_metadata": metadata}

    # ── Extract Google Meet link from references ─────────────────────
    from services.cal_service import CalService
    meet_link = CalService.extract_meet_link(booking)

    if not meet_link:
        # Try top-level videoCallUrl
        meet_link = booking.get("videoCallUrl") or booking.get("video_call_url")

    if not meet_link:
        logger.warning(
            f"⚠️ Cal.com booking {cal_booking_id} for ticket {ticket_id} "
            f"has no Google Meet link in references"
        )

    # ── Update hitl_ticket ───────────────────────────────────────────
    start_time = booking.get("startTime") or booking.get("start_time")
    success = _hitl_service.update_booking(
        ticket_id=ticket_id,
        cal_booking_id=cal_booking_id,
        booking_url=meet_link,
        meeting_time=start_time
    )

    if not success:
        logger.error(f"❌ Failed to update booking on ticket {ticket_id}")
        raise HTTPException(status_code=500, detail="Failed to update booking record")

    logger.info(
        f"✅ Cal.com booking confirmed | ticket={ticket_id} | "
        f"cal_id={cal_booking_id} | meet={meet_link}"
    )

    # ── Send confirmation emails (non-blocking) ──────────────────────
    try:
        # Fetch ticket to get user and lawyer emails (now included in get_ticket_by_id)
        ticket = _hitl_service.get_ticket_by_id(ticket_id)
        if ticket and _email_service:
            user_email = ticket.get("user_email")
            user_name = ticket.get("user_display_name") or "User"
            lawyer_email = ticket.get("lawyer_email")
            lawyer_name = ticket.get("lawyer_name") or "Lawyer"
            start_time = booking.get("startTime") or booking.get("start_time") or ""

            if user_email and meet_link:
                # 1. Notify User
                await _email_service.send_booking_confirmation_email(
                    to_email=user_email,
                    user_name=user_name,
                    meet_link=meet_link,
                    start_time=start_time,
                )
                
                # 2. Notify Lawyer
                if lawyer_email:
                    await _email_service.send_booking_confirmation_email(
                        to_email=lawyer_email,
                        user_name=lawyer_name,
                        meet_link=meet_link,
                        start_time=start_time,
                    )
                    logger.info(f"📧 Confirmation emails sent to user ({user_email}) and lawyer ({lawyer_email})")
                else:
                    logger.info(f"📧 Confirmation email sent to user ({user_email}) | No lawyer email found")
    except Exception as notify_exc:
        # Non-fatal — webhook still succeeds
        logger.warning(f"⚠️ Booking confirmation emails failed (non-fatal) | {notify_exc}")

    return {
        "status": "success",
        "ticket_id": ticket_id,
        "cal_booking_id": cal_booking_id,
        "booking_url": meet_link,
    }