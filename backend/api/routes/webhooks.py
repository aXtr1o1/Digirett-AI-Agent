import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from svix.webhooks import Webhook, WebhookVerificationError

from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

_user_service = None

def set_services(user_service) -> None:
    global _user_service
    _user_service = user_service


@router.post(
    "/clerk",
    tags=["Webhooks"],
    summary="Handle Clerk user events",
)
async def clerk_webhook(
    request: Request,
    svix_id: str = Header(None, alias="svix-id"),
    svix_timestamp: str = Header(None, alias="svix-timestamp"),
    svix_signature: str = Header(None, alias="svix-signature"),
):
    """
    Webhook handler for Clerk events (user.created, user.updated).
    Requires Svix signature verification to prevent spoofing.
    """
    if not settings.CLERK_WEBHOOK_SECRET:
        logger.error("❌ CLERK_WEBHOOK_SECRET is not set")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured",
        )

    if not svix_id or not svix_timestamp or not svix_signature:
        logger.warning("⚠️ Missing Svix headers")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Svix headers",
        )

    payload = await request.body()
    headers = {
        "svix-id": svix_id,
        "svix-timestamp": svix_timestamp,
        "svix-signature": svix_signature,
    }

    try:
        wh = Webhook(settings.CLERK_WEBHOOK_SECRET)
        evt = wh.verify(payload, headers)
    except WebhookVerificationError as exc:
        logger.warning(f"⚠️ Invalid webhook signature: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        )
    except Exception as exc:
        logger.error(f"❌ Webhook verification error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )

    event_type = evt.get("type")
    data = evt.get("data", {})
    logger.info(f"📩 Received Clerk webhook: {event_type}")

    if event_type == "user.created":
        clerk_user_id = data.get("id")
        
        # Get primary email
        email_addresses = data.get("email_addresses", [])
        primary_email_id = data.get("primary_email_address_id")
        email = ""
        for ea in email_addresses:
            if ea.get("id") == primary_email_id:
                email = ea.get("email_address")
                break
        if not email and email_addresses:
            email = email_addresses[0].get("email_address", "")

        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        display_name = f"{first_name} {last_name}".strip()
        if not display_name:
            display_name = email.split("@")[0] if email else "User"

        # Check if user already exists
        if _user_service.user_exists(clerk_user_id):
            logger.info(f"ℹ️ User already exists (duplicate webhook?): {clerk_user_id}")
            return {"status": "ignored", "reason": "User already exists"}

        try:
            # Note: We assign DEFAULT_TENANT_ID here. In a real multi-tenant app, 
            # this logic would be more complex.
            tenant_id = settings.DEFAULT_TENANT_ID
            if not tenant_id:
                # Fallback tenant ID if not set in config
                tenant_id = "00000000-0000-0000-0000-000000000000"
                
            _user_service.create_user_from_webhook(
                clerk_user_id=clerk_user_id,
                email=email,
                tenant_id=tenant_id,
                display_name=display_name,
            )
            return {"status": "success", "message": "User created"}
        except Exception as exc:
            logger.error(f"❌ Failed to process user.created: {exc}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user",
            )

    # Ignore other events
    return {"status": "ignored", "reason": f"Unhandled event type: {event_type}"}
