import logging
import httpx
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CalService:
    """
    CalService — handles interaction with Cal.com API v2.
    """

    # Cal.com API v2 Base URL
    BASE_URL = "https://api.cal.com/v2"

    def __init__(self) -> None:
        logger.info("📅 CalService initialized (API v2)")

    async def get_available_slots(
        self,
        cal_api_key: str,
        event_type_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timezone: str = "Europe/Oslo",
    ) -> Dict[str, Any]:
        """
        Fetches available slots for a specific event type using Cal.com API v2.
        
        Args:
            start_date: YYYY-MM-DD (defaults to today)
            end_date:   YYYY-MM-DD (defaults to 7 days from now)
        """
        if not start_date:
            start_date = datetime.utcnow().strftime("%Y-%m-%d")
        if not end_date:
            end_date = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")

        url = f"{self.BASE_URL}/slots/available"
        params = {
            "eventTypeId": event_type_id,
            "startTime": f"{start_date}T00:00:00Z",
            "endTime": f"{end_date}T23:59:59Z",
            "timeZone": timezone,
        }

        headers = {
            "Authorization": f"Bearer {cal_api_key}",
            "Content-Type": "application/json",
            "cal-api-version": "2024-06-11" # Required version header for v2
        }

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, params=params, headers=headers, timeout=15.0)
                
                if resp.status_code != 200:
                    error_detail = resp.text
                    logger.error(f"❌ Cal.com slots fetch failed | status={resp.status_code} | {error_detail}")
                    raise ValueError(f"Cal.com API error {resp.status_code}: {error_detail}")

                data = resp.json()
                # v2 returns slots in a slightly different structure: data['data']['slots']
                result = data.get("data", {})
                logger.info(
                    f"📅 Cal.com slots fetched | event_type={event_type_id} | "
                    f"days={len(result.get('slots', {}))}"
                )
                return result

            except httpx.RequestError as exc:
                logger.error(f"❌ Network error fetching Cal.com slots | {exc}")
                raise ValueError(f"Failed to connect to Cal.com: {exc}")

    async def create_booking(
        self,
        cal_api_key: str,
        event_type_id: int,
        start_time: str,
        user_name: str,
        user_email: str,
        ticket_id: str,
        conversation_id: str,
        timezone: str = "Europe/Oslo",
    ) -> Dict[str, Any]:
        """
        Creates a booking on Cal.com v2.
        Passes ticketId and conversationId in the metadata so the webhook can link it back.
        """
        url = f"{self.BASE_URL}/bookings"
        
        payload = {
            "eventTypeId": event_type_id,
            "start": start_time,
            "responses": {
                "name": user_name,
                "email": user_email,
            },
            "metadata": {
                "ticketId": ticket_id,
                "conversationId": conversation_id
            },
            "timeZone": timezone,
            "language": "en"
        }

        headers = {
            "Authorization": f"Bearer {cal_api_key}",
            "Content-Type": "application/json",
            "cal-api-version": "2024-06-11"
        }

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
                
                if resp.status_code not in (200, 201):
                    error_detail = resp.text
                    logger.error(f"❌ Cal.com booking failed | status={resp.status_code} | {error_detail}")
                    raise ValueError(f"Cal.com Booking error {resp.status_code}: {error_detail}")

                result = resp.json()
                data = result.get("data", result)
                logger.info(f"✅ Cal.com booking created | id={data.get('id')} | ticket={ticket_id}")
                return data

            except httpx.RequestError as exc:
                logger.error(f"❌ Network error creating Cal.com booking | {exc}")
                raise ValueError(f"Failed to connect to Cal.com: {exc}")

    @staticmethod
    def extract_meet_link(booking_payload: Dict[str, Any]) -> Optional[str]:
        """
        Helper to find the Google Meet or Video URL in a Cal.com booking payload.
        Handles both v1 and v2 webhook formats.
        Prioritizes actual Google Meet/Zoom links, and uses Cal.com branded
        video links for Cal Video (Daily) rather than direct Daily.co links.
        """
        # 1. Check references for external integrations (Google Meet, Zoom, etc.)
        references = booking_payload.get("references", [])
        for ref in references:
            ref_url = ref.get("meetingUrl") or ref.get("url") or ""
            if ref_url:
                # If it's Google Meet, Zoom, or Teams, return it immediately
                if "meet.google.com" in ref_url or "zoom.us" in ref_url or "teams.microsoft.com" in ref_url:
                    return ref_url

        # 2. Check for Cal Video / Daily.co
        # If it's a daily.co link, we want to redirect to the Cal.com video page instead
        uid = booking_payload.get("uid")
        metadata = booking_payload.get("metadata") or {}
        
        # If there is a videoCallUrl in metadata, use it
        video_call_url = metadata.get("videoCallUrl")
        if video_call_url and "cal.com" in video_call_url:
            return video_call_url

        # Otherwise, if we have a uid, we can construct the Cal.com video link
        if uid:
            return f"https://app.cal.com/video/{uid}"

        # 3. Fallback to any meetingUrl in references (even if it's daily.co)
        for ref in references:
            ref_url = ref.get("meetingUrl") or ref.get("url")
            if ref_url:
                return ref_url

        # 4. Fallback to top level meetingUrl or videoCallUrl
        if booking_payload.get("meetingUrl"):
            return booking_payload["meetingUrl"]
            
        return booking_payload.get("videoCallUrl") or booking_payload.get("video_call_url")
