"""
services/cal_service.py — Cal.com REST API integration

Responsibilities:
- Fetch available time slots for a specific lawyer (using their own Cal.com API key
  and event type ID stored in lawyer_profiles)
- Create a booking on the lawyer's calendar with user details and metadata
- Each lawyer has their own Cal.com account (cal_api_key + cal_event_type_id
  stored in the lawyer_profiles table)

Cal.com v1 API base: https://api.cal.com/v1
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

CAL_API_BASE = "https://api.cal.com/v1"


class CalService:
    """
    Thin async wrapper around Cal.com REST API v1.
    Each method accepts the lawyer's personal Cal.com API key so this service
    is stateless — no credentials are stored on the service itself.
    """

    def __init__(self) -> None:
        logger.info("✅ CalService initialized")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SLOTS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def get_available_slots(
        self,
        cal_api_key: str,
        event_type_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timezone: str = "Europe/Oslo",
    ) -> Dict[str, Any]:
        """
        Fetch available time slots for a lawyer using Cal.com's GET /v1/slots.

        Args:
            cal_api_key:    Lawyer's own Cal.com API key (from lawyer_profiles).
            event_type_id:  The specific event type ID (from lawyer_profiles).
            start_date:     ISO date string YYYY-MM-DD. Defaults to today.
            end_date:       ISO date string YYYY-MM-DD. Defaults to today + 7 days.
            timezone:       IANA timezone for slot display. Defaults to Oslo.

        Returns:
            Cal.com slot response dict with `slots` key mapping dates → time slots.
            Example:
              {
                "slots": {
                  "2026-05-15": [
                    {"time": "2026-05-15T09:00:00+02:00"},
                    {"time": "2026-05-15T10:00:00+02:00"}
                  ]
                }
              }

        Raises:
            ValueError on API error or missing credentials.
        """
        if not cal_api_key or not event_type_id:
            raise ValueError("cal_api_key and event_type_id are required for slot fetching.")

        now = datetime.utcnow()
        start = start_date or now.strftime("%Y-%m-%d")
        end = end_date or (now + timedelta(days=7)).strftime("%Y-%m-%d")

        params = {
            "apiKey": cal_api_key,
            "eventTypeId": event_type_id,
            "startTime": f"{start}T00:00:00.000Z",
            "endTime": f"{end}T23:59:59.999Z",
            "timeZone": timezone,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{CAL_API_BASE}/slots", params=params)

            if response.status_code != 200:
                logger.error(
                    f"❌ Cal.com slots fetch failed | status={response.status_code} | {response.text[:300]}"
                )
                raise ValueError(f"Cal.com API error {response.status_code}: {response.text[:200]}")

            data = response.json()
            logger.info(
                f"📅 Cal.com slots fetched | event_type={event_type_id} | "
                f"days={len(data.get('slots', {}))}"
            )
            return data

        except httpx.RequestError as exc:
            logger.error(f"❌ Cal.com network error | {exc}")
            raise ValueError(f"Network error fetching slots: {exc}") from exc

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BOOKINGS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def create_booking(
        self,
        cal_api_key: str,
        event_type_id: int,
        start_time: str,
        user_name: str,
        user_email: str,
        conversation_id: str,
        ticket_id: str,
        timezone: str = "Europe/Oslo",
        language: str = "en",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a booking on the lawyer's Cal.com calendar via POST /v1/bookings.

        Args:
            cal_api_key:      Lawyer's Cal.com API key.
            event_type_id:    The lawyer's event type ID.
            start_time:       ISO 8601 datetime of the chosen slot, e.g. "2026-05-15T09:00:00Z"
            user_name:        Full name of the user being booked.
            user_email:       Email of the user being booked.
            conversation_id:  Our internal conversation UUID (stored as metadata).
            ticket_id:        Our HITL ticket UUID (stored as metadata).
            timezone:         IANA timezone.
            language:         Cal.com locale.
            metadata:         Any extra metadata to attach to the booking.

        Returns:
            Cal.com booking response dict. Key fields:
              - id:        Cal.com booking ID
              - uid:       Booking UID
              - startTime: Confirmed start time
              - endTime:   Confirmed end time
              - references: list of {type, uid, meetingUrl} — Google Meet link lives here

        Raises:
            ValueError on API error.
        """
        if not cal_api_key or not event_type_id:
            raise ValueError("cal_api_key and event_type_id are required for booking.")

        extra_meta = metadata or {}
        extra_meta.update({
            "conversationId": conversation_id,
            "ticketId": ticket_id,
            "source": "digirett-hitl",
        })

        payload = {
            "eventTypeId": event_type_id,
            "start": start_time,
            "timeZone": timezone,
            "language": language,
            "responses": {
                "name": user_name,
                "email": user_email,
            },
            "metadata": extra_meta,
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{CAL_API_BASE}/bookings",
                    params={"apiKey": cal_api_key},
                    json=payload,
                )

            if response.status_code not in (200, 201):
                logger.error(
                    f"❌ Cal.com booking failed | status={response.status_code} | {response.text[:300]}"
                )
                raise ValueError(f"Cal.com booking error {response.status_code}: {response.text[:200]}")

            data = response.json()
            logger.info(
                f"📅 Cal.com booking created | id={data.get('id')} | "
                f"ticket={ticket_id} | start={start_time}"
            )
            return data

        except httpx.RequestError as exc:
            logger.error(f"❌ Cal.com network error during booking | {exc}")
            raise ValueError(f"Network error creating booking: {exc}") from exc

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def extract_meet_link(booking_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract the Google Meet link from a Cal.com booking response.

        Cal.com stores the meet link in booking.references[].meetingUrl
        where type is "google_meet_video" or similar.

        Falls back to videoCallUrl if present at the top level.
        """
        # Try references array first (most reliable)
        references = booking_data.get("references") or []
        for ref in references:
            meeting_url = ref.get("meetingUrl") or ref.get("meeting_url")
            if meeting_url:
                return meeting_url

        # Fallback: top-level videoCallUrl (some Cal.com versions)
        return booking_data.get("videoCallUrl") or booking_data.get("video_call_url")
