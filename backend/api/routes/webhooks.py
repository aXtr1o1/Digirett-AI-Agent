import logging
import stripe
from datetime import datetime
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
        logger.error(f" Webhook verification error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )

    event_type = evt.get("type")
    data = evt.get("data", {})
    logger.info(f" Received Clerk webhook: {event_type}")

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
                logger.info(f" Sending custom Clerk email | to={to_email} | subject={subject}")
                success = await _email_service.send_clerk_email(
                    to_email=to_email,
                    subject=subject,
                    html_content=body_html,
                    plain_content=body_plain,
                )
                if not success:
                    logger.error(" Failed to send custom Clerk email via SMTP")
                    # Even if it fails, return 200 so Clerk doesn't keep retrying indefinitely,
                    # or return 500 if we want Clerk to retry. Returning 500 is safer for delivery guarantees.
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to send custom email",
                    )
                return {"status": "success", "message": "Custom email sent"}
            else:
                logger.warning(" Email payload missing recipient or email_service not initialized")
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
            logger.info(f" User already exists (duplicate webhook?): {clerk_user_id}")
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
            logger.error(f" Failed to process user.created: {exc}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user",
            )

    # Ignore other events
    return {"status": "ignored", "reason": f"Unhandled event type: {event_type}"}


@router.post(
    "/stripe",
    tags=["Webhooks"],
    summary="Handle Stripe webhook events",
)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
):
    """
    Webhook handler for Stripe checkout session completions.
    Updates the database schema and Clerk metadata when a user completes their subscription.
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
    except stripe.error.SignatureVerificationError as e:
        logger.warning(f" Invalid Stripe signature: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        )
    except Exception as exc:
        logger.error(f" Stripe verification error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bad Request",
        )

    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})

    logger.info(f" Received Stripe webhook: {event_type}")

    if event_type == "customer.subscription.updated":
        customer_id = data_object.get("customer")
        if not customer_id:
            logger.warning(" No customer ID found in subscription updated event")
            return {"status": "ignored", "reason": "No customer ID"}
        
        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            customer = stripe.Customer.retrieve(customer_id)
            email = customer.get("email")
            
            if not email:
                logger.warning(f" No email found for Stripe customer {customer_id}")
                return {"status": "ignored", "reason": "No customer email"}
            
            # Determine plan tier from product name
            plan_tier = "free_trial"
            items = data_object.get("items", {}).get("data", [])
            if items:
                product_id = items[0].get("plan", {}).get("product")
                if product_id:
                    product = stripe.Product.retrieve(product_id)
                    item_name = product.get("name", "").lower()
                    if "start-up" in item_name or "startup" in item_name:
                        plan_tier = "start_up"
                    elif "vekst" in item_name:
                        plan_tier = "vekst"
                    elif "smb" in item_name:
                        plan_tier = "smb"
                    elif "enterprise" in item_name:
                        plan_tier = "enterprise"

            logger.info(f"💳 Stripe subscription updated to '{plan_tier}' for customer email: {email}")

            if _user_service:
                # Find user by email in Supabase
                user_res = _user_service._supabase.table("users").select("clerk_user_id").eq("email", email).execute()
                if user_res.data:
                    clerk_user_id = user_res.data[0].get("clerk_user_id")
                    
                    # 1. Update Supabase
                    try:
                        update_query = _user_service._supabase.table("users").update({
                            "plan_tier": plan_tier,
                            "role": plan_tier,
                            "updated_at": datetime.utcnow().isoformat()
                        }).eq("clerk_user_id", clerk_user_id)
                        _user_service._supabase.execute_query(update_query)
                        logger.info(f" DB plan_tier updated to '{plan_tier}' for email: {email}")
                    except Exception as db_exc:
                        logger.error(f" Supabase update failed for user {clerk_user_id}: {db_exc}")

                    # 2. Update Clerk Metadata
                    try:
                        _user_service._sync_clerk_metadata(clerk_user_id, {
                            "role": plan_tier,
                            "plan_tier": plan_tier
                        })
                        logger.info(f" Clerk metadata updated to '{plan_tier}' for user {clerk_user_id}")
                    except Exception as clerk_exc:
                        logger.error(f" Clerk metadata update failed for user {clerk_user_id}: {clerk_exc}")
                else:
                    logger.warning(f" No user profile found in database matching email {email}")

        except Exception as exc:
            logger.error(f" Subscription update webhook process error: {exc}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Webhook process failed",
            )

    if event_type == "customer.subscription.deleted":
        customer_id = data_object.get("customer")
        if not customer_id:
            logger.warning(" No customer ID found in subscription deleted event")
            return {"status": "ignored", "reason": "No customer ID"}
        
        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            customer = stripe.Customer.retrieve(customer_id)
            email = customer.get("email")
            
            if not email:
                logger.warning(f" No email found for Stripe customer {customer_id}")
                return {"status": "ignored", "reason": "No customer email"}
            
            if _user_service:
                # Find user by email in Supabase
                user_res = _user_service._supabase.table("users").select("clerk_user_id").eq("email", email).execute()
                if user_res.data:
                    clerk_user_id = user_res.data[0].get("clerk_user_id")
                    
                    # 1. Update Supabase
                    try:
                        update_query = _user_service._supabase.table("users").update({
                            "plan_tier": "free_trial",
                            "role": "user",
                            "updated_at": datetime.utcnow().isoformat()
                        }).eq("clerk_user_id", clerk_user_id)
                        _user_service._supabase.execute_query(update_query)
                        logger.info(f" DB subscription cancelled for email: {email}")
                    except Exception as db_exc:
                        logger.error(f" Supabase update failed for user {clerk_user_id}: {db_exc}")

                    # 2. Update Clerk Metadata
                    try:
                        _user_service._sync_clerk_metadata(clerk_user_id, {
                            "role": "user",
                            "plan_tier": "free_trial"
                        })
                        logger.info(f" Clerk metadata reset for user {clerk_user_id}")
                    except Exception as clerk_exc:
                        logger.error(f" Clerk metadata reset failed for user {clerk_user_id}: {clerk_exc}")
                else:
                    logger.warning(f" No user profile found in database matching email {email}")

        except Exception as exc:
            logger.error(f" Subscription cancellation webhook process error: {exc}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Webhook process failed",
            )

    if event_type == "checkout.session.completed":
        clerk_user_id = data_object.get("client_reference_id")
        session_id = data_object.get("id")

        if not clerk_user_id:
            logger.warning(" No client_reference_id found in Stripe Checkout Session")
            return {"status": "ignored", "reason": "No client_reference_id"}

        try:
            # Query checkout session detail from Stripe to find line items
            stripe.api_key = settings.STRIPE_SECRET_KEY
            session = stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
            line_items = session.get("line_items", {}).get("data", [])
            
            plan_tier = "free_trial"
            if line_items:
                item_name = line_items[0].get("description", "").lower()
                if "start-up" in item_name or "startup" in item_name:
                    plan_tier = "start_up"
                elif "vekst" in item_name:
                    plan_tier = "vekst"
                elif "smb" in item_name:
                    plan_tier = "smb"
                elif "enterprise" in item_name:
                    plan_tier = "enterprise"

            logger.info(f" Stripe payment verified for user {clerk_user_id} | Plan determined: {plan_tier}")

            if _user_service:
                # Update Supabase database
                try:
                    update_query = _user_service._supabase.table("users").update({
                        "plan_tier": plan_tier,
                        "role": plan_tier,
                        "updated_at": datetime.utcnow().isoformat()
                    }).eq("clerk_user_id", clerk_user_id)
                    _user_service._supabase.execute_query(update_query)
                    logger.info(f" DB updated plan_tier to '{plan_tier}' for Clerk ID: {clerk_user_id}")
                except Exception as db_exc:
                    logger.error(f" Supabase database update failed for user {clerk_user_id} | {db_exc}")

                # Update Clerk auth metadata so the frontend updates instantly
                try:
                    _user_service._sync_clerk_metadata(clerk_user_id, {
                        "role": plan_tier,
                        "plan_tier": plan_tier
                    })
                    logger.info(f" Clerk metadata successfully updated for Clerk ID: {clerk_user_id}")
                except Exception as clerk_exc:
                    logger.error(f" Clerk metadata update failed for user {clerk_user_id} | {clerk_exc}")

        except Exception as exc:
            logger.error(f" Stripe session retrieval error: {exc}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Transaction verification failed",
            )

    return {"status": "success"}


