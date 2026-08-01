"""
services/cal_service.py — Cal.com Integration Service
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
import httpx
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

CAL_API_VERSION = "2024-06-11"


class CalApiException(HTTPException):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)


class BookingResponse(BaseModel):
    id: str
    uid: Optional[str] = None
    status: str
    event_type_id: Optional[int] = None
    raw_data: Dict[str, Any] = Field(default_factory=dict)


class SlotResponse(BaseModel):
    slots: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)


class CalService:
    BASE_URL = "https://api.cal.com/v2"

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=15.0)
        logger.info("[OK] CalService initialized (Persistent HTTP Client Pool)")

    @staticmethod
    def extract_meet_link(booking: Any) -> Optional[str]:
        """Extract meeting URL (Google Meet, Zoom, Daily.co) from Cal.com booking data."""
        if not booking:
            return None

        data = booking.raw_data if hasattr(booking, "raw_data") else (booking if isinstance(booking, dict) else {})

        # 1. Direct top-level meeting URL attributes
        for key in ("meetingUrl", "meeting_url", "videoCallUrl", "video_call_url", "locationUrl", "location_url"):
            if data.get(key):
                return str(data[key])

        # 2. Check metadata dictionary
        meta = data.get("metadata") or {}
        if isinstance(meta, dict):
            for key in ("videoCallUrl", "video_call_url", "meetingUrl", "meeting_url"):
                if meta.get(key):
                    return str(meta[key])

        # 3. Check references array
        refs = data.get("references") or []
        uid = data.get("uid")
        if isinstance(refs, list):
            for ref in refs:
                if isinstance(ref, dict):
                    ref_type = str(ref.get("type", "")).lower()
                    if ref_type == "daily_video" and uid:
                        return f"https://app.cal.com/video/{uid}"
                    if ref.get("meetingUrl"):
                        return str(ref["meetingUrl"])

        return None

    def _build_headers(self, cal_api_key: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {cal_api_key}",
            "Content-Type": "application/json",
            "cal-api-version": CAL_API_VERSION,
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=3), reraise=True)
    async def get_available_slots(
        self,
        cal_api_key: str,
        event_type_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timezone: str = "Europe/Oslo",
    ) -> SlotResponse:
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
        headers = self._build_headers(cal_api_key)

        try:
            resp = await self._client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                logger.error(f"❌ Cal.com slots fetch failed | status={resp.status_code} | {resp.text}")
                raise CalApiException(status_code=resp.status_code, detail=f"Cal.com slots fetch failed: {resp.text}")

            data = resp.json().get("data", {})
            return SlotResponse(slots=data.get("slots", {}))
        except httpx.RequestError as exc:
            logger.error(f"❌ Network error fetching Cal.com slots | {exc}")
            raise CalApiException(status_code=503, detail=f"Network error connecting to Cal.com: {exc}") from exc

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=3), reraise=True)
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
    ) -> BookingResponse:
        url = f"{self.BASE_URL}/bookings"
        payload = {
            "eventTypeId": event_type_id,
            "start": start_time,
            "language": "en",
            "responses": {
                "name": user_name,
                "email": user_email,
                "language": "en",
            },
            "metadata": {
                "ticketId": ticket_id,
                "conversationId": conversation_id,
            },
            "timeZone": timezone,
        }
        headers = self._build_headers(cal_api_key)

        try:
            resp = await self._client.post(url, json=payload, headers=headers)
            if resp.status_code not in (200, 201):
                logger.error(f"❌ Cal.com booking failed | status={resp.status_code} | {resp.text}")
                raise CalApiException(status_code=resp.status_code, detail=f"Cal.com booking creation failed: {resp.text}")

            data = resp.json().get("data", {})
            return BookingResponse(
                id=str(data.get("id", "")),
                uid=data.get("uid"),
                status=data.get("status", "accepted"),
                event_type_id=event_type_id,
                raw_data=data,
            )
        except httpx.RequestError as exc:
            logger.error(f"❌ Network error creating Cal.com booking | {exc}")
            raise CalApiException(status_code=503, detail=f"Network error connecting to Cal.com: {exc}") from exc
