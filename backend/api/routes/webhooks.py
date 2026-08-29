import logging
from typing import Optional

try:
    import stripe
except ImportError:
    stripe = None

try:
    from svix.webhooks import Webhook, WebhookVerificationError
except ImportError:
    Webhook = None
    WebhookVerificationError = Exception

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from config import settings
from schemas.responses import WebhookResponse
from services.webhook_service import WebhookService

logger = logging.getLogger(__name__)
router = APIRouter()

def get_webhook_service(request: Request) -> WebhookService:
    svc = getattr(request.app.state, "webhook_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WebhookService is not initialized on application state.",
        )
    return svc

@router.post(
    "/clerk",
    response_model=WebhookResponse,
    tags=["Webhooks"],
    summary="Handle Clerk user events",
)
async def clerk_webhook(
    request: Request,
    svix_id: str = Header(None, alias="svix-id"),
    svix_timestamp: str = Header(None, alias="svix-timestamp"),
    svix_signature: str = Header(None, alias="svix-signature"),
    webhook_service: WebhookService = Depends(get_webhook_service),
):
    if not settings.CLERK_WEBHOOK_SECRET:
        logger.error(" CLERK_WEBHOOK_SECRET is not set")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured",
        )

    if not svix_id or not svix_timestamp or not svix_signature:
        logger.warning(" Missing Svix headers")
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
        logger.warning(f" Invalid webhook signature: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        )
    except Exception as exc:
        logger.exception(f" Webhook verification error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )

    res = await webhook_service.handle_clerk_event(evt, event_id=svix_id)
    return WebhookResponse(**res)


@router.post(
    "/stripe",
    response_model=WebhookResponse,
    tags=["Webhooks"],
    summary="Handle Stripe webhook events",
)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    webhook_service: WebhookService = Depends(get_webhook_service),
):
    """
    Webhook handler for Stripe checkout session completions and subscription updates.
    Enforces idempotency and delegates synchronization to SubscriptionService.
    """
    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error(" STRIPE_WEBHOOK_SECRET is not set")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe webhook secret not configured",
        )

    if not stripe_signature:
        logger.warning(" Missing Stripe signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe signature",
        )

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError as exc:
        logger.warning(f" Invalid Stripe signature: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        )
    except Exception as exc:
        logger.exception(f" Stripe verification error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bad Request",
        )

    event_id = event.get("id")
    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})

    logger.info(f" Received Stripe webhook: {event_type} | event_id={event_id}")

    if event_type in ("customer.subscription.updated", "checkout.session.completed"):
        clerk_user_id = data_object.get("client_reference_id")
        item_name = ""

        if event_type == "checkout.session.completed" and clerk_user_id:
            session_id = data_object.get("id")
            stripe.api_key = settings.STRIPE_SECRET_KEY
            session = stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
            line_items = session.get("line_items", {}).get("data", [])
            if line_items:
                item_name = line_items[0].get("description", "")

        if clerk_user_id:
            res = webhook_service.sync_stripe_subscription(clerk_user_id, item_name, event_id=event_id)
            return WebhookResponse(**res)

    return WebhookResponse(status="success", message="Event processed")