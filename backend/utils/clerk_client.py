"""
utils/clerk_client.py — Clerk HTTP API Integration Client Wrapper
"""

import logging
from typing import Any, Dict, Optional
import httpx

from config import settings

logger = logging.getLogger(__name__)


class ClerkClient:
    

    def __init__(self, secret_key: Optional[str] = None) -> None:
        self._secret_key = secret_key or settings.CLERK_SECRET_KEY
        self._base_url = "https://api.clerk.com/v1"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._secret_key}",
            "Content-Type": "application/json",
        }

    async def get_user(self, clerk_user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch Clerk user profile metadata by clerk_user_id."""
        if not clerk_user_id or not self._secret_key:
            return None
        url = f"{self._base_url}/users/{clerk_user_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f" Clerk get_user failed | status={resp.status_code} | id={clerk_user_id}")
                return None
        except Exception as exc:
            logger.error(f" ClerkClient get_user error | id={clerk_user_id} | {exc}")
            return None

    async def update_user_metadata(
        self,
        clerk_user_id: str,
        public_metadata: Dict[str, Any],
    ) -> bool:
        """Update publicMetadata for a user in Clerk."""
        if not clerk_user_id or not self._secret_key:
            return False
        url = f"{self._base_url}/users/{clerk_user_id}"
        payload = {"public_metadata": public_metadata}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.patch(url, headers=self._headers(), json=payload)
                if resp.status_code in (200, 204):
                    logger.info(f" Clerk user public_metadata updated | id={clerk_user_id}")
                    return True
                logger.warning(f" Clerk update_user_metadata failed | status={resp.status_code} | id={clerk_user_id}")
                return False
        except Exception as exc:
            logger.error(f" ClerkClient update_user_metadata error | id={clerk_user_id} | {exc}")
            return False
