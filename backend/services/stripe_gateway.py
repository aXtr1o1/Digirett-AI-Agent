"""
services/stripe_gateway.py — Stripe API Gateway integration

Encapsulates direct Stripe SDK operations (Customer lookups, Customer retrieval,
Billing Portal Session creation) offloaded to threadpools using asyncio.to_thread
so synchronous SDK calls never block FastAPI's async event loop.
"""

import asyncio
import logging
from typing import Optional, Dict, Any

import stripe

logger = logging.getLogger(__name__)


class StripeGateway:

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        stripe.api_key = api_key
        logger.info("[OK] StripeGateway initialized")

    async def get_customer_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Locates a Stripe Customer matching the given email address.
        Offloaded to a worker thread via asyncio.to_thread.
        """
        def _sync_lookup():
            stripe.api_key = self._api_key
            customers = stripe.Customer.list(email=email, limit=1)
            if customers.data:
                c = customers.data[0]
                return {"id": c.id, "email": getattr(c, "email", None)}
            return None

        try:
            return await asyncio.to_thread(_sync_lookup)
        except Exception as exc:
            logger.error(f"❌ Stripe Customer lookup by email failed | email={email} | {exc}")
            raise exc

    async def get_customer_by_id(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a Stripe Customer by customer_id.
        Offloaded to a worker thread via asyncio.to_thread.
        """
        def _sync_retrieve():
            stripe.api_key = self._api_key
            c = stripe.Customer.retrieve(customer_id)
            if c and not getattr(c, "deleted", False):
                return {"id": c.id, "email": getattr(c, "email", None)}
            return None

        try:
            return await asyncio.to_thread(_sync_retrieve)
        except Exception as exc:
            logger.error(f"❌ Stripe Customer retrieval by ID failed | customer_id={customer_id} | {exc}")
            raise exc

    async def create_portal_session(self, customer_id: str, return_url: str) -> str:
        """
        Creates a Stripe Customer Portal Session URL.
        Offloaded to a worker thread via asyncio.to_thread.
        """
        def _sync_create():
            stripe.api_key = self._api_key
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return session.url

        try:
            return await asyncio.to_thread(_sync_create)
        except Exception as exc:
            logger.error(f"❌ Stripe Portal Session creation failed | customer_id={customer_id} | {exc}")
            raise exc
