import logging
from typing import Optional, Dict, Any

from config import settings
from services.stripe_gateway import StripeGateway
from services.user_service import UserService

logger = logging.getLogger(__name__)


class BillingService:

    def __init__(self, stripe_gateway: StripeGateway, user_service: UserService) -> None:
        self._gateway = stripe_gateway
        self._user_service = user_service
        logger.info("[OK] BillingService initialized")

    def _log_audit(self, action: str, performer_id: Optional[str], payload: Dict[str, Any]) -> None:
        """Saves entry to the audit_logs table via user_service internal client."""
        try:
            if hasattr(self._user_service, "_log_audit"):
                self._user_service._log_audit(action, performer_id, payload)
        except Exception as exc:
            logger.warning(f" Billing audit log failed (non-fatal) | {action} | {exc}")

    async def get_or_resolve_customer(self, user_id: str, email: str) -> Optional[str]:
        """
        Resolves the Stripe customer ID for a user.
        1. Checks stored stripe_customer_id on the user record in database.
        2. If not found, uses StripeGateway to search Stripe by email.
        3. Saves resolved stripe_customer_id back to user record for instant future lookups.
        """
        # Step 1: Check database for cached customer ID
        customer_id = self._user_service.get_stripe_customer_id(user_id)
        if customer_id:
            return customer_id

        # Step 2: Fallback — search Stripe by email (for existing users)
        if not email:
            logger.warning(f"[WARN] Cannot perform Stripe email fallback for user {user_id}: missing email")
            return None

        stripe_customer = await self._gateway.get_customer_by_email(email)
        if not stripe_customer:
            return None

        customer_id = stripe_customer["id"]

        # Step 3: Cache resolved customer_id back to users table
        self._user_service.set_stripe_customer_id(user_id, customer_id)
        logger.info(f" Cached Stripe customer ID {customer_id} for user {user_id}")
        return customer_id

    async def create_portal_session(self, clerk_user_id: str, email: Optional[str] = None) -> Dict[str, Any]:
        """
        Orchestrates Customer Portal creation:
        - Resolves user email and internal user_id
        - Resolves & caches stripe_customer_id with fallback
        - Verifies customer ownership against email
        - Generates Portal Session URL via StripeGateway
        - Logs audit event `billing.portal_accessed`
        """
        # 1. Resolve internal user_id & email
        user_id = self._user_service.get_user_id_from_clerk_id(clerk_user_id)
        if not user_id:
            user_info = None
        else:
            user_info = self._user_service.get_user_by_id(user_id)

        user_email = email or (user_info.get("email") if user_info else None)
        if not user_email:
            return {"success": False, "status_code": 400, "detail": "User email address is missing."}

        internal_user_id = user_id or clerk_user_id

        # 2. Resolve customer ID (cached DB query or Stripe email search fallback)
        customer_id = await self.get_or_resolve_customer(user_id=internal_user_id, email=user_email)
        if not customer_id:
            return {
                "success": False,
                "status_code": 404,
                "detail": "No Stripe customer profile found matching this account.",
            }

        # 3. Ownership verification: Verify customer email matches user email
        customer_data = await self._gateway.get_customer_by_id(customer_id)
        if not customer_data:
            return {
                "success": False,
                "status_code": 404,
                "detail": "Stripe customer profile no longer exists.",
            }

        stripe_email = customer_data.get("email")
        if stripe_email and stripe_email.lower() != user_email.lower():
            logger.warning(
                f" Ownership verification failed! User email={user_email} mismatch with Stripe email={stripe_email}"
            )
            return {
                "success": False,
                "status_code": 403,
                "detail": "Customer ownership verification failed.",
            }

        # 4. Generate Billing Customer Portal session URL via Gateway
        return_url = f"{settings.FRONTEND_URL}/chat?billing_update=true"
        portal_url = await self._gateway.create_portal_session(customer_id=customer_id, return_url=return_url)

        # 5. Audit log access event
        self._log_audit(
            action="billing.portal_accessed",
            performer_id=internal_user_id,
            payload={"customer_id": customer_id, "email": user_email},
        )

        return {
            "success": True,
            "status_code": 200,
            "url": portal_url,
        }
