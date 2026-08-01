"""
api/routes/billing.py — Billing customer portal endpoints

Refactored according to TL code review guidelines:
- Pure FastAPI Dependency Injection via Request.app.state
- Delegated business logic to BillingService & StripeGateway
- Zero direct Stripe SDK or Supabase database calls in route handler
- Explicit BillingPortalResponse model for Swagger contracts & type safety
- Granular HTTP exception status codes (400, 403, 404, 500)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, HttpUrl

from core.auth import ClerkUser, get_current_user
from services.billing_service import BillingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])


def get_billing_service(request: Request) -> BillingService:
    svc = getattr(request.app.state, "billing_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BillingService is not initialized on application state.",
        )
    return svc


# ── Schemas ──────────────────────────────────────────────────────────

class BillingPortalResponse(BaseModel):
    status: str = "success"
    url: HttpUrl


# ── Endpoints ────────────────────────────────────────────────────────

@router.post(
    "/portal-session",
    summary="Create Stripe Billing Customer Portal session",
    response_model=BillingPortalResponse,
)
async def create_portal_session(
    current_user: ClerkUser = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service),
):
    """
    Creates a Stripe billing customer portal session URL for the active user,
    allowing them to manage payment methods, view invoices, or cancel subscriptions.
    """
    logger.info(f"Generating billing portal session | user={current_user.clerk_user_id}")

    result = await billing_service.create_portal_session(
        clerk_user_id=current_user.clerk_user_id,
        email=current_user.email,
    )

    if not result.get("success"):
        status_code = result.get("status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
        detail = result.get("detail", "Failed to generate Stripe billing portal session.")
        raise HTTPException(status_code=status_code, detail=detail)

    return BillingPortalResponse(
        status="success",
        url=result["url"],
    )
