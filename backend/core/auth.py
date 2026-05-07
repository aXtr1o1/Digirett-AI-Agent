"""
core/auth.py — Clerk JWT verification + role-based access middleware

HOW IT WORKS:
1. Every HTTP request that needs auth passes through `get_current_user()`.
   It reads the `Authorization: Bearer <token>` header, verifies the JWT
   against Clerk's JWKS endpoint (RS256), and returns a `ClerkUser` dict
   with clerk_user_id, email, and role.

2. `require_role(*allowed_roles)` is a FastAPI dependency that wraps
   `get_current_user()` and checks if the user's role is in the
   allowed set. Returns 403 if not.

3. For WebSocket routes (chat), use `verify_ws_token(token)` directly
   since FastAPI dependencies don't work on raw WebSocket handlers.

JWKS CACHING:
Clerk's JWKS (public keys) are fetched once at startup and cached in-memory.
They auto-refresh every 6 hours or on verification failure (key rotation).
"""

import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

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
    Keys: clerk_user_id, email, role
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

        # Verify and decode the JWT
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            options={
                "verify_aud": False,  # Clerk doesn't always set audience
                "verify_iss": False,  # We validate via JWKS instead
            },
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
    except JWTError as exc:
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

async def get_current_user(request: Request) -> ClerkUser:
    """
    FastAPI dependency — extracts and verifies the Clerk JWT from the
    Authorization header. Returns a ClerkUser dict.

    Usage:
        @router.get("/foo")
        async def foo(user: ClerkUser = Depends(get_current_user)):
            print(user.clerk_user_id, user.role)
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
        )
    return await verify_token(auth_header)


def require_role(*allowed_roles: str):
    """
    FastAPI dependency factory — checks that the authenticated user
    has one of the specified roles.

    Usage:
        @router.get("/admin/users")
        async def list_users(user: ClerkUser = Depends(require_role("admin"))):
            ...

        @router.get("/lawyer/tickets")
        async def tickets(user: ClerkUser = Depends(require_role("lawyer", "admin"))):
            ...
    """
    async def _role_checker(user: ClerkUser = Depends(get_current_user)) -> ClerkUser:
        if user.role not in allowed_roles:
            logger.warning(
                f"⛔ Access denied | user={user.clerk_user_id} "
                f"role={user.role} | required={allowed_roles}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(allowed_roles)}",
            )
        return user

    return _role_checker


def require_db_role(*allowed_roles: str):
    """
    FastAPI dependency factory — checks that the authenticated user has one of the allowed
    roles according to the authoritative role stored in the Supabase `users` table.
    """
    async def _db_role_checker(user: ClerkUser = Depends(get_current_user)) -> ClerkUser:
        # Resolve internal user record to get the DB role
        from db.supabase_client import get_supabase
        supabase = get_supabase()
        try:
            resp = supabase.table("users").select("role").eq("clerk_user_id", user.clerk_user_id).single().execute()
            db_role = resp.data.get("role") if resp.data else None
        except Exception as exc:
            logger.error(f"❌ DB role check failed for {user.clerk_user_id} | {exc}")
            db_role = None
        if db_role not in allowed_roles:
            logger.warning(
                f"⛔ Access denied (DB role) | user={user.clerk_user_id} role={db_role} required={allowed_roles}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(allowed_roles)}",
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
