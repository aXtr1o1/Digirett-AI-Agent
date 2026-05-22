import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from svix.webhooks import Webhook, WebhookVerificationError

from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

_user_service = None
_email_service = None

def set_services(user_service, email_service=None) -> None:
    global _user_service, _email_service
    _user_service = user_service
    _email_service = email_service


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
    Webhook handler for Clerk events (user.created, user.updated, email.created).
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

    if event_type == "email.created":
        # Handle custom email delivery from Clerk
        delivered_by_clerk = data.get("delivered_by_clerk")
        
        # Only process if Clerk is NOT delivering it
        if delivered_by_clerk is False:
            to_email = data.get("to_email_address")
            subject = data.get("subject", "Notification from Digirett")
            body_html = data.get("body", "")
            body_plain = data.get("body_plain", "")
            
            if to_email and _email_service:
                logger.info(f"📧 Sending custom Clerk email | to={to_email} | subject={subject}")
                success = await _email_service.send_clerk_email(
                    to_email=to_email,
                    subject=subject,
                    html_content=body_html,
                    plain_content=body_plain,
                )
                if not success:
                    logger.error("❌ Failed to send custom Clerk email via SMTP")
                    # Even if it fails, return 200 so Clerk doesn't keep retrying indefinitely,
                    # or return 500 if we want Clerk to retry. Returning 500 is safer for delivery guarantees.
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to send custom email",
                    )
                return {"status": "success", "message": "Custom email sent"}
            else:
                logger.warning("⚠️ Email payload missing recipient or email_service not initialized")
                return {"status": "error", "reason": "Missing data or service"}
        else:
            return {"status": "ignored", "reason": "delivered_by_clerk is true"}

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

        first_name = data.get("first_name") or ""
        last_name = data.get("last_name") or ""
        username = data.get("username") or ""

        # Use first + last name if they exist, otherwise use the username
        display_name = f"{first_name} {last_name}".strip() or username
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
                username=username,
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

