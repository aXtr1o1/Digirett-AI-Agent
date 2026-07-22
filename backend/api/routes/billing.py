import logging
import stripe
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

from core.auth import ClerkUser, get_current_user
from services.user_service import UserService
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["Billing"])

_user_service: Optional[UserService] = None

def set_services(user_service: UserService) -> None:
    global _user_service
    _user_service = user_service

@router.post(
    "/portal-session",
    summary="Create Stripe Billing Customer Portal session",
)
async def create_portal_session(
    current_user: ClerkUser = Depends(get_current_user)
):
    """
    Creates a Stripe billing customer portal session URL for the active user,
    allowing them to manage payment methods, view invoices, or cancel their subscription.
    """
    if not _user_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service not initialized",
        )

    clerk_user_id = current_user.clerk_user_id
    email = current_user.email

    try:
        # 1. Resolve email address
        if not email:
            user_res = _user_service._supabase.table("users").select("email").eq("clerk_user_id", clerk_user_id).execute()
            if not user_res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User profile not found in database",
                )
            email = user_res.data[0].get("email")

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User email not found. Cannot locate Stripe customer profile.",
            )

        # 2. Locate customer in Stripe using email
        stripe.api_key = settings.STRIPE_SECRET_KEY
        customers = stripe.Customer.list(email=email, limit=1)
        if not customers.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No Stripe customer profile found matching this account's email.",
            )
        
        customer_id = customers.data[0].id

        # 3. Create billing portal session
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{settings.FRONTEND_URL}/chat?billing_update=true"
        )

        return {"status": "success", "url": session.url}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as exc:
        logger.error(f"❌ Stripe Billing Portal session creation error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate Stripe billing portal session.",
        )
