import logging
import time
from typing import Any, Dict, List, Optional
import json
import httpx
from fastapi import Depends, HTTPException, Request, status

import jwt
from jwt import PyJWTError
from jwt.algorithms import RSAAlgorithm
from config import settings

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# JWKS cache — Clerk uses RS256 (asymmetric). We fetch public keys
# from Clerk's .well-known/jwks.json and cache them in-memory.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_jwks_cache: Dict[str, Any] = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SECONDS = 6 * 3600  # Refresh every 6 hours


async def _fetch_jwks() -> Dict[str, Any]:
    """Fetch JWKS from Clerk's well-known endpoint."""
    global _jwks_cache, _jwks_fetched_at

    jwks_url = settings.CLERK_JWKS_URL
    if not jwks_url:
        raise RuntimeError(
            "CLERK_JWKS_URL is not configured. "
            "Set it to https://<your-clerk-domain>/.well-known/jwks.json"
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(jwks_url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_fetched_at = time.time()
            logger.info(
                f"🔑 JWKS fetched from Clerk | keys={len(_jwks_cache.get('keys', []))}"
            )
            return _jwks_cache
    except Exception as exc:
        logger.error(f"❌ Failed to fetch JWKS from {jwks_url} | {exc}")
        raise RuntimeError(f"JWKS fetch failed: {exc}") from exc


async def _get_jwks() -> Dict[str, Any]:
    """Return cached JWKS, refreshing if stale or empty."""
    global _jwks_cache, _jwks_fetched_at

    now = time.time()
    if not _jwks_cache or (now - _jwks_fetched_at) > _JWKS_TTL_SECONDS:
        return await _fetch_jwks()
    return _jwks_cache


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# JWT verification
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ClerkUser(dict):
    """
    A dict subclass returned by get_current_user().
    Keys: clerk_user_id, email, role, db_user_id, status
    """
    @property
    def clerk_user_id(self) -> str:
        return self["clerk_user_id"]

    @property
    def role(self) -> str:
        return self.get("role", "user")

    @property
    def email(self) -> Optional[str]:
        return self.get("email")

    @property
    def db_user_id(self) -> Optional[str]:
        return self.get("db_user_id")

    @property
    def db_role(self) -> Optional[str]:
        return self.get("db_role")

    @property
    def is_suspended(self) -> bool:
        return self.get("status") == "suspended"


async def verify_token(token: str) -> ClerkUser:
    """
    Verify a Clerk JWT and extract user info.

    Returns ClerkUser with keys:
        - clerk_user_id: str (Clerk's `sub` claim)
        - email: str | None
        - role: str (from publicMetadata in JWT, default 'user')

    Raises HTTPException(401) on invalid/expired tokens.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required",
        )

    # Strip "Bearer " prefix if present
    if token.startswith("Bearer "):
        token = token[7:]

    try:
        jwks = await _get_jwks()

        # Decode header to find the correct key
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        # Find matching key in JWKS
        rsa_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = key
                break

        if not rsa_key:
            # Key not found — maybe rotated. Force refresh and retry once.
            logger.warning("⚠️ JWT kid not found in cached JWKS — refreshing")
            jwks = await _fetch_jwks()
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    rsa_key = key
                    break

        if not rsa_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token signing key not found",
            )
        # Convert Clerk's JWK dictionary into an RSA public key.
        public_key = RSAAlgorithm.from_jwk(json.dumps(rsa_key))

        # Options for verify_iss and verify_aud
        decode_options = {
            "verify_aud": bool(getattr(settings, "CLERK_AUDIENCE", None)),
            "verify_iss": bool(getattr(settings, "CLERK_ISSUER", None)),
            "require": ["exp", "iat", "sub"],
        }
        decode_kwargs = {
            "algorithms": ["RS256"],
            "options": decode_options,
            "leeway": 60,
        }
        if getattr(settings, "CLERK_ISSUER", None):
            decode_kwargs["issuer"] = settings.CLERK_ISSUER
        if getattr(settings, "CLERK_AUDIENCE", None):
            decode_kwargs["audience"] = settings.CLERK_AUDIENCE

        # Verify and decode the Clerk JWT.
        payload = jwt.decode(
            token,
            public_key,
            **decode_kwargs,
        )

        clerk_user_id = payload.get("sub")
        if not clerk_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject claim",
            )

        # Extract role from Clerk's publicMetadata (embedded in JWT)
        # Clerk puts publicMetadata at the root level of the JWT payload
        metadata = payload.get("publicMetadata") or payload.get("public_metadata") or {}
        role = metadata.get("role", "user")

        # Extract email if available
        email = payload.get("email")
        # Sometimes Clerk puts email in different fields
        if not email:
            email = payload.get("email_address")
        if not email:
            # Check the primary email from Clerk's email_addresses array
            emails = payload.get("email_addresses") or []
            if emails and isinstance(emails, list):
                email = emails[0] if isinstance(emails[0], str) else emails[0].get("email_address")

        return ClerkUser({
            "clerk_user_id": clerk_user_id,
            "email": email,
            "role": role,
        })

    except HTTPException:
        raise
    except PyJWTError as exc:
        logger.warning(f"⚠️ JWT verification failed | {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
        )
    except Exception as exc:
        logger.error(f"❌ Token verification error | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FastAPI dependencies
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Request, WebSocket

class WebSocketFriendlyBearer(HTTPBearer):
    async def __call__(self, request: Request = None, websocket: WebSocket = None) -> Optional[HTTPAuthorizationCredentials]:
        req = request or websocket
        auth_header = req.headers.get("Authorization")
        if not auth_header and getattr(req, "query_params", None):
            auth_header = req.query_params.get("token")
            
        if auth_header:
            return HTTPAuthorizationCredentials(scheme="Bearer", credentials=auth_header.replace("Bearer ", ""))
        return None

security_bearer = WebSocketFriendlyBearer(auto_error=False)

async def get_current_user(request: Request = None, websocket: WebSocket = None, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)) -> ClerkUser:
    """
    FastAPI dependency — extracts and verifies the Clerk JWT or Static API Key from the
    Authorization header (or query param for WebSockets). Returns a ClerkUser dict.
    
    Now also verifies the user's status in the database to enforce 
    suspensions and role authoritative state.
    """
    req = request or websocket
    auth_header = req.headers.get("Authorization", "")
    if not auth_header and getattr(req, "query_params", None):
        auth_header = req.query_params.get("token", "")

    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
        )
    
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header
    
    # 0. Check for Static API Key (restricted to non-production environments)
    is_prod = getattr(settings, "ENVIRONMENT", "development").lower() == "production"
    if not is_prod and hasattr(settings, "BACKEND_API_KEY") and settings.BACKEND_API_KEY and token == settings.BACKEND_API_KEY:
        return ClerkUser({
            "clerk_user_id": "swagger_admin",
            "email": "admin@digirett.no",
            "role": "admin",
            "db_user_id": "swagger_admin",
            "db_role": "admin",
            "status": "active"
        })
    
    # 1. Verify Clerk JWT
    user = await verify_token(auth_header)
    
    # 2. Authoritative enrichment from Supabase
    from db.supabase_client import get_supabase
    return await enrich_user_from_database(user, get_supabase())


async def enrich_user_from_database(user: ClerkUser, supabase: Any) -> ClerkUser:
    """Shared helper to fetch and attach database role and status to ClerkUser."""
    if not user or not user.clerk_user_id:
        return user

    import asyncio
    try:
        def fetch_user_status():
            query = supabase.table("users") \
                .select("user_id, role, status") \
                .eq("clerk_user_id", user.clerk_user_id) \
                .limit(1)
            return supabase.execute_query(query)

        resp = await asyncio.to_thread(fetch_user_status)

        if resp and resp.data:
            db_user = resp.data[0] if isinstance(resp.data, list) else resp.data
            if db_user.get("status") == "suspended":
                logger.warning(f"🚫 Suspended user attempt | user={user.clerk_user_id}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your account has been suspended. Please contact support."
                )

            user["db_user_id"] = db_user.get("user_id")
            user["db_role"] = db_user.get("role")
            user["status"] = db_user.get("status")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"⚠️ User status check failed | {exc}")

    return user


def require_role(*allowed_roles: str):
    """
    FastAPI dependency factory — checks that the authenticated user
    has one of the specified roles.
    """
    async def _role_checker(user: ClerkUser = Depends(get_current_user)) -> ClerkUser:
        allowed = list(allowed_roles)
        if "admin" in allowed and "system_admin" not in allowed:
            allowed.append("system_admin")
        if "lawyer" in allowed and "system_admin" not in allowed:
            allowed.append("system_admin")

        if user.role not in allowed:
            logger.warning(
                f"⛔ Access denied | user={user.clerk_user_id} "
                f"role={user.role} | required={allowed}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(allowed)}",
            )
        return user

    return _role_checker


def require_db_role(*allowed_roles: str):
    """
    FastAPI dependency factory — checks that the authenticated user has one of the allowed
    roles according to the authoritative role stored in the Supabase `users` table.
    """
    async def _db_role_checker(user: ClerkUser = Depends(get_current_user)) -> ClerkUser:
        db_role = user.db_role
        if not db_role:
            from db.supabase_client import get_supabase
            user = await enrich_user_from_database(user, get_supabase())
            db_role = user.db_role

        allowed = list(allowed_roles)
        if "admin" in allowed and "system_admin" not in allowed:
            allowed.append("system_admin")
        if "lawyer" in allowed and "system_admin" not in allowed:
            allowed.append("system_admin")

        if db_role not in allowed:
            logger.warning(
                f"⛔ Access denied (DB role) | user={user.clerk_user_id} role={db_role} required={allowed}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(allowed)}",
            )
        return user
    return _db_role_checker



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WebSocket token helper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def verify_ws_token(token: Optional[str]) -> Optional[ClerkUser]:
    """
    Verify a JWT token for WebSocket connections.
    Returns ClerkUser on success, None on failure (caller decides action).

    The frontend sends the token as a query param or in the first WS message:
        ws://host/api/v1/chat/ws?token=<jwt>
    """
    if not token:
        return None
    try:
        return await verify_token(token)
    except HTTPException:
        return None
    except Exception:
        return None