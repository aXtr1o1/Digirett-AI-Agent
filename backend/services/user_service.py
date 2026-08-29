"""
services/user_service.py — User CRUD operations against Supabase

This service handles:
- Creating user + profile rows when Clerk webhook fires
- Looking up users by clerk_user_id (for resolving JWT → Supabase user_id)
- Role checks against the DB (supplement to JWT role)

The Supabase `users` table is the source of truth for role data.
Clerk publicMetadata is kept in sync but the DB is authoritative.
"""

import logging
import httpx
from datetime import datetime
from typing import Any, Dict, Optional, List
from pydantic import BaseModel
from uuid import uuid4

from functools import lru_cache
from config import settings

from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

class AcceptInviteResult(BaseModel):

    success: bool
    status_code: int = 200
    detail: str = ""
    role: Optional[str] = None
    invited_by: Optional[str] = None


from utils.clerk_client import ClerkClient

class UserService:

    def __init__(self, supabase_client: SupabaseClient) -> None:
        self._supabase = supabase_client
        self._clerk = ClerkClient()
        logger.info("[OK] UserService initialized with ClerkClient")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CREATE (called by Clerk webhook handler)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def create_user_from_webhook(
        self,
        clerk_user_id: str,
        email: str,
        tenant_id: str,
        display_name: Optional[str] = None,
        phone: Optional[str] = None,
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new user + user_profiles row from Clerk webhook data.
        Called when Clerk fires `user.created`.

        Returns the created user dict.
        """
        try:
            now = datetime.utcnow().isoformat()
            user_id = str(uuid4())

            # ── Check for pending invitation ─────────────────────────────
            assigned_role = "user"
            invite_data = None
            try:
                invite_resp = self._supabase.table("role_invites").select("*").eq("email", email).eq("status", "pending").execute()
                if invite_resp.data:
                    invite_data = invite_resp.data[0]
                    assigned_role = invite_data["role"]
                    logger.info(f"🎁 Found invitation for {email} | role={assigned_role}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to check role_invites for {email} | {e}")

            # ── Insert into users table ──────────────────────────────────
            # NOTE: tenant_id is kept as None for now — multi-tenancy is
            # scoped to a future phase. The column + FK stays in the schema
            # but we don't enforce a real tenant row yet.
            _PLACEHOLDER_TENANT = "00000000-0000-0000-0000-000000000000"
            safe_tenant_id = None if (not tenant_id or tenant_id == _PLACEHOLDER_TENANT) else tenant_id

            user_data = {
                "user_id": user_id,
                "clerk_user_id": clerk_user_id,
                "email": email,
                "mail_id": email,
                "user_name": username or display_name or email.split("@")[0],
                "role": assigned_role,
                "status": "active",
                "tenant_id": safe_tenant_id,
                "created_at": now,
                "updated_at": now,
            }

            response = self._supabase.table("users").insert(user_data).execute()
            user_row = response.data[0] if response.data else user_data

            # ── Insert into user_profiles table ──────────────────────────
            profile_data = {
                "user_id": user_id,
                "display_name": display_name or email.split("@")[0],
                "phone_number": phone,
                "created_at": now,
                "updated_at": now,
            }
            self._supabase.table("user_profiles").insert(profile_data).execute()

            # ── Handle Role-Specific Profiles & Invitations ──────────────
            # Fetch Clerk details if possible to get full name
            clerk_details = self._get_clerk_user_details(clerk_user_id)
            full_name = clerk_details.get("full_name") if clerk_details else display_name

            if assigned_role == "lawyer":
                self._supabase.table("lawyer_profiles").insert({
                    "lawyer_id": user_id,
                    "full_name": full_name,
                    "verification_status": "approved",
                    "created_at": now,
                    "updated_at": now
                }).execute()
            elif assigned_role == "admin":
                self._supabase.table("admin_profiles").insert({
                    "admin_id": user_id,
                    "full_name": full_name,
                    "created_by": invite_data.get("invited_by") if invite_data else None,
                    "created_at": now,
                    "updated_at": now
                }).execute()

            if invite_data:
                # Mark invite as accepted
                self._supabase.table("role_invites").update({"status": "accepted"}).eq("invite_id", invite_data["invite_id"]).execute()
                # Log audit
                self._log_audit("user.signup_from_invite", user_id, {"role": assigned_role, "invite_id": invite_data["invite_id"]})
                # Sync Clerk Metadata (important: webhook happens AFTER clerk user creation)
                self._sync_clerk_role(clerk_user_id, assigned_role)

            logger.info(
                f"[OK] Created user | user_id={user_id} | "
                f"clerk_id={clerk_user_id} | email={email} | role={assigned_role}"
            )
            return user_row

        except Exception as exc:
            logger.error(
                f"[ERROR] create_user_from_webhook failed | clerk_id={clerk_user_id} | {exc}",
                exc_info=True,
            )
            raise ValueError(f"Failed to create user: {exc}") from exc

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # READ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_user_by_clerk_id(self, clerk_user_id: str) -> Optional[Dict[str, Any]]:
        """Look up a user by their Clerk user ID."""
        try:
            response = (
                self._supabase.table("users")
                .select("*")
                .eq("clerk_user_id", clerk_user_id)
                .limit(1)
                .execute()
            )
            if response.data:
                return response.data[0]
            return None
        except Exception as exc:
            logger.error(f"[ERROR] get_user_by_clerk_id failed | {exc}")
            return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Look up a user by their Supabase user_id (UUID)."""
        try:
            response = (
                self._supabase.table("users")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if response.data:
                return response.data[0]
            return None
        except Exception as exc:
            logger.error(f"[ERROR] get_user_by_id failed | {exc}")
            return None

    def get_user_id_from_clerk_id(self, clerk_user_id: str, email: str = None) -> Optional[str]:
        """
        Quick lookup: Clerk user ID -> Supabase user_id.
        Auto-creates the user in Supabase if missing.
        """
        logger.info(f"🔍 DEBUG: get_user_id_from_clerk_id | clerk_id={clerk_user_id} | provided_email={email}")
        user = self.get_user_by_clerk_id(clerk_user_id)
        if user:
            logger.info(f"[OK] Found existing user: {user['user_id']}")
            return user["user_id"]

        logger.info(f"[INFO] User {clerk_user_id} not found in Supabase. Attempting auto-creation...")
        # If user not found, auto-create them (fallback for missing webhook)
        try:
            real_email = email
            display_name = None
            
            # If no email provided, try to fetch from Clerk API
            if not real_email and settings.CLERK_SECRET_KEY:
                logger.info(f"[INFO] Fetching email from Clerk API for {clerk_user_id}...")
                clerk_url = f"https://api.clerk.com/v1/users/{clerk_user_id}"
                try:
                    with httpx.Client() as client:
                        resp = client.get(clerk_url, headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"})
                        if resp.status_code == 200:
                            data = resp.json()
                            print(data)
                            email_addresses = data.get("email_addresses", [])
                            if email_addresses:
                                real_email = email_addresses[0].get("email_address")
                                logger.info(f"[INFO] Fetched email: {real_email}")
                            
                            username = data.get("username")
                            display_name = username
                        else:
                            logger.error(f"[ERROR] Clerk API returned {resp.status_code}: {resp.text}")
                except Exception as e:
                    logger.error(f"[ERROR] Clerk API request failed: {e}")

            fallback_email = real_email or f"{clerk_user_id}@placeholder.com"
            logger.info(f"[INFO] Calling create_user_from_webhook with email: {fallback_email}")
            
            # Final check: Does this email already exist?
            try:
                existing_email_resp = self._supabase.table("users").select("user_id, clerk_user_id").eq("email", fallback_email).execute()
                if existing_email_resp.data:
                    existing = existing_email_resp.data[0]
                    logger.error(f"[ERROR] EMAIL CONFLICT: Email {fallback_email} is already used by Supabase user {existing['user_id']} (Clerk ID: {existing['clerk_user_id']})")
                    # Optionally: Update the clerk_user_id if it's the same person but different Clerk instance? 
                    # For now, just return the existing ID to unblock them, or fail clearly.
                    return existing["user_id"]
            except Exception as e:
                logger.warning(f"[WARN] Email uniqueness check failed (non-fatal): {e}")

            new_user = self.create_user_from_webhook(
                clerk_user_id=clerk_user_id,
                email=fallback_email,
                tenant_id=None,
                display_name=display_name,
                username=display_name # we set username to display_name in fallback
            )
            logger.info(f"[OK] Successfully auto-created user: {new_user.get('user_id')}")
            return new_user.get("user_id")
        except Exception as exc:
            logger.error(f"[ERROR] FATAL: Auto-creation failed for {clerk_user_id} | {exc}", exc_info=True)

        return None

    def user_exists(self, clerk_user_id: str) -> bool:
        """Check if a user already exists (prevent duplicate webhook processing)."""
        return self.get_user_by_clerk_id(clerk_user_id) is not None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # UPDATE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def update_role(
        self,
        user_id: str,
        new_role: str,
    ) -> bool:
        """Update a user's role in Supabase. Called by admin promotion endpoints."""
        try:
            self._supabase.table("users").update({
                "role": new_role,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("user_id", user_id).execute()

            logger.info(f"[OK] Updated role | user_id={user_id} → {new_role}")
            return True
        except Exception as exc:
            logger.error(f"[ERROR] update_role failed | user_id={user_id} | {exc}")
            return False

    def suspend_user(self, user_id: str) -> bool:
        """Set user status to 'suspended' and sync to Clerk."""
        try:
            # 1. Update DB
            self._supabase.table("users").update({
                "status": "suspended",
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("user_id", user_id).execute()

            # 2. Sync to Clerk (set role to suspended to block frontend)
            user = self.get_user_by_id(user_id)
            if user:
                self._sync_clerk_role(user["clerk_user_id"], "suspended")

            logger.info(f"[OK] Suspended user | user_id={user_id}")
            return True
        except Exception as exc:
            logger.error(f"[ERROR] suspend_user failed | {exc}")
            return False

    def reactivate_user(self, user_id: str) -> bool:
        """Set user status back to 'active' and restore role in Clerk."""
        try:
            # 1. Update DB
            self._supabase.table("users").update({
                "status": "active",
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("user_id", user_id).execute()

            # 2. Sync to Clerk (restore their actual role)
            user = self.get_user_by_id(user_id)
            if user:
                self._sync_clerk_role(user["clerk_user_id"], user["role"])

            logger.info(f"[OK] Reactivated user | user_id={user_id}")
            return True
        except Exception as exc:
            logger.error(f"[ERROR] reactivate_user failed | {exc}")
            return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ROLE MANAGEMENT (PHASE 2)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def accept_invite(self, token: str, clerk_user_id: str, email: str) -> AcceptInviteResult:

        """
        Accepts a pending invitation. Validates the token and email, 
        promotes the user, and marks the invite as accepted.
        Returns an AcceptInviteResult detailing the outcome status, role, and details.
        """
        try:
            # 1. Look up the invite
            resp = self._supabase.table("role_invites").select("*").eq("token", token).execute()
            if not resp.data:
                logger.warning(f"[WARN] Invite token not found: {token}")
                return AcceptInviteResult(success=False, status_code=404, detail="Invitation token not found.")

            invite = resp.data[0]
            if invite.get("status") != "pending":
                logger.warning(f"[WARN] Invite token already accepted/revoked: {token} (status={invite.get('status')})")
                return AcceptInviteResult(success=False, status_code=410, detail="Invitation token has already been accepted or revoked.")

            # 2. Get user_id from clerk_id
            user_id = self.get_user_id_from_clerk_id(clerk_user_id)
            if not user_id:
                logger.error(f"[ERROR] Could not find internal user_id for clerk_id: {clerk_user_id}")
                return AcceptInviteResult(success=False, status_code=404, detail="User account not found.")

            user_info = self.get_user_by_id(user_id)
            if not user_info:
                logger.error(f"[ERROR] Could not find user info for user_id: {user_id}")
                return AcceptInviteResult(success=False, status_code=404, detail="User record not found.")

            db_email = user_info.get("email")
            invite_email = invite.get("email")

            if not invite_email or not db_email:
                logger.warning(f"[WARN] Missing email for verification. Token email: {invite_email}, DB email: {db_email}")
                return AcceptInviteResult(success=False, status_code=400, detail="Missing email for token verification.")

            if invite_email.lower() != db_email.lower():
                logger.warning(f"[WARN] Invite email mismatch. Token email: {invite_email}, DB email: {db_email}")
                return AcceptInviteResult(success=False, status_code=403, detail=f"This invitation token belongs to {invite_email}, not {db_email}.")

            role = invite["role"]
            current_role = user_info.get("role", "user")

            if role == "lawyer":
                if current_role == "admin":
                    logger.info(f"[INFO] Dual-role detected for Admin {user_id}. Creating lawyer profile...")
                    success = self.enable_lawyer_dashboard_for_admin(user_id=user_id, admin_id=user_id)
                else:
                    success = await self.promote_to_lawyer(user_id=user_id, admin_id=None, bar_license="PENDING", bar_council="PENDING")
            elif role == "admin":
                full_name = user_info.get("user_name") if user_info else "Admin"
                success = await self.promote_to_admin(user_id=user_id, admin_id="system", full_name=full_name)
            elif role == "system_admin":
                success = await self.promote_to_system_admin(user_id=user_id, admin_id="system")
            else:
                success = True

            if not success:
                return AcceptInviteResult(success=False, status_code=500, detail="Failed to update user role.")

            # Mark invite as accepted
            self._supabase.table("role_invites").update({"status": "accepted"}).eq("invite_id", invite["invite_id"]).execute()

            # Audit log
            self._log_audit("user.invite_accepted", user_id, {"role": role, "invite_id": invite["invite_id"]})

            logger.info(f"[OK] Invite accepted for {email} -> {role}")
            return AcceptInviteResult(
                success=True,
                status_code=200,
                detail="Invitation accepted. Role updated.",
                role=role,
                invited_by=invite.get("invited_by"),
            )

        except Exception as exc:
            logger.error(f"[ERROR] accept_invite failed | {exc}")
            return AcceptInviteResult(success=False, status_code=500, detail=f"Internal server error: {str(exc)}")



    async def invite_user(self, email: str, role: str, admin_id: str, email_service: Any, admin_email: Optional[str] = None) -> bool:
        """
        Generates an invitation token, saves it to role_invites, and sends an email.
        """
        try:
            # 1. Check if user already exists with a privileged role
            existing_user_resp = self._supabase.table("users").select("role").eq("email", email).execute()
            if existing_user_resp.data:
                existing_role = existing_user_resp.data[0].get("role", "user")
                # Allow Admin to invite themselves as a Lawyer
                if existing_role == "lawyer" or (existing_role == "admin" and role == "admin") or (existing_role == "system_admin" and role == "system_admin"):
                    logger.warning(f"[WARN] User {email} already has role {existing_role}. Invitation blocked.")
                    raise ValueError(f"An account with this email is already registered as a {existing_role.capitalize()}. Duplicate invitations are restricted.")

            token = str(uuid4())
            invite_data = {
                "email": email,
                "role": role,
                "token": token,
                "status": "pending",
                "invited_by": admin_id,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Upsert (allow re-inviting or updating role)
            upsert_query = self._supabase.table("role_invites").upsert(invite_data, on_conflict="email")
            self._supabase.execute_query(upsert_query)
            
            # Send email (await async call)
            success = await email_service.send_invitation_email(email, role, token, admin_email=admin_email)
            
            if success:
                self._log_audit("admin.user_invited", admin_id, {"target_email": email, "role": role})
                logger.info(f"📨 Invited user | email={email} | role={role}")
                return True
            return False
        except ValueError as exc:
            raise exc
        except Exception as exc:
            logger.error(f"❌ invite_user failed | {email} | {exc}")
            return False

    def get_all_invitations(self) -> List[Dict[str, Any]]:
        """
        Fetches all rows from the role_invites table.
        """
        try:
            query = self._supabase.table("role_invites").select("*").order("created_at", desc=True)
            resp = self._supabase.execute_query(query)
            return resp.data or []
        except Exception as exc:
            logger.error(f"❌ get_all_invitations failed | {exc}")
            return []

    def revoke_invitation(self, invite_id: str) -> bool:
        """
        Deletes a pending invitation from the role_invites table.
        """
        try:
            query = self._supabase.table("role_invites").delete().eq("invite_id", invite_id)
            resp = self._supabase.execute_query(query)
            return len(resp.data or []) > 0
        except Exception as exc:
            logger.error(f"❌ revoke_invitation failed | {invite_id} | {exc}")
            return False

    def promote_to_lawyer(self, user_id: str, admin_id: str, bar_license: str = None, bar_council: str = None) -> bool:
        """Promotes a user to Lawyer role and creates their profile."""
        try:
            user = self.get_user_by_id(user_id)
            if not user: return False
            
            now = datetime.utcnow().isoformat()
            
            # 1. Update users table
            self._supabase.table("users").update({
                "role": "lawyer",
                "updated_at": now
            }).eq("user_id", user_id).execute()
            
            # 2. Insert into lawyer_profiles
            clerk_details = self._get_clerk_user_details(user["clerk_user_id"])
            full_name = clerk_details.get("full_name") if clerk_details else user.get("user_name")

            self._supabase.table("lawyer_profiles").upsert({
                "lawyer_id": user_id,
                "full_name": full_name,
                "bar_license_number": bar_license,
                "bar_council": bar_council,
                "verification_status": "approved",
                "verified_by": admin_id if admin_id != "system" else None,
                "verified_at": now,
                "updated_at": now
            }).execute()
            
            # 3. Sync Clerk
            self._sync_clerk_role(user["clerk_user_id"], "lawyer")
            
            # 4. Audit
            self._log_audit("admin.user_promoted", admin_id, {"target_user_id": user_id, "new_role": "lawyer"})
            
            return True
        except Exception as exc:
            logger.error(f"❌ promote_to_lawyer failed | {user_id} | {exc}")
            return False

    def promote_to_admin(self, user_id: str, admin_id: str, full_name: str = None) -> bool:
        """Promotes a user to Admin role."""
        try:
            user = self.get_user_by_id(user_id)
            if not user: return False
            
            now = datetime.utcnow().isoformat()
            
            # 1. Update users table
            self._supabase.table("users").update({
                "role": "admin",
                "updated_at": now
            }).eq("user_id", user_id).execute()
            
            # 2. Insert into admin_profiles
            if not full_name:
                clerk_details = self._get_clerk_user_details(user["clerk_user_id"])
                full_name = clerk_details.get("full_name") if clerk_details else user.get("user_name")

            self._supabase.table("admin_profiles").upsert({
                "admin_id": user_id,
                "full_name": full_name,
                "created_by": admin_id,
                "updated_at": now
            }).execute()
            
            # 3. Sync Clerk
            self._sync_clerk_role(user["clerk_user_id"], "admin")
            
            # 4. Audit
            self._log_audit("admin.user_promoted", admin_id, {"target_user_id": user_id, "new_role": "admin"})
            
            return True
        except Exception as exc:
            logger.error(f"❌ promote_to_admin failed | {user_id} | {exc}")
            return False

    def promote_to_system_admin(self, user_id: str, admin_id: str) -> bool:
        """Promotes a user to System Admin role."""
        try:
            user = self.get_user_by_id(user_id)
            if not user: return False
            
            now = datetime.utcnow().isoformat()
            
            # 1. Update users table
            self._supabase.table("users").update({
                "role": "system_admin",
                "updated_at": now
            }).eq("user_id", user_id).execute()
            
            # 2. Sync Clerk
            self._sync_clerk_role(user["clerk_user_id"], "system_admin")
            
            # 3. Audit
            self._log_audit("admin.user_promoted", admin_id, {"target_user_id": user_id, "new_role": "system_admin"})
            
            return True
        except Exception as exc:
            logger.error(f"❌ promote_to_system_admin failed | {user_id} | {exc}")
            return False

    def enable_lawyer_dashboard_for_admin(self, user_id: str, admin_id: str) -> bool:
        """Adds a lawyer profile to an existing admin without changing their role."""
        try:
            user = self.get_user_by_id(user_id)
            if not user or user.get("role") != "admin":
                return False

            now = datetime.utcnow().isoformat()
            
            # 1. Ensure lawyer_profiles entry exists
            clerk_details = self._get_clerk_user_details(user["clerk_user_id"])
            full_name = clerk_details.get("full_name") if clerk_details else user.get("user_name")

            self._supabase.table("lawyer_profiles").upsert({
                "lawyer_id": user_id,
                "full_name": full_name,
                "verification_status": "approved",
                "verified_by": admin_id if admin_id != "system" else None,
                "verified_at": now,
                "updated_at": now
            }).execute()

            # 2. Sync Clerk Metadata with the new flag
            self._sync_clerk_metadata(user["clerk_user_id"], {"role": "admin", "has_lawyer_dashboard": True})
            
            # 3. Audit
            self._log_audit("admin.dual_role_enabled", admin_id, {"target_user_id": user_id})
            return True
        except Exception as exc:
            logger.error(f"❌ enable_lawyer_dashboard_for_admin failed | {user_id} | {exc}")
            return False

    def get_lawyer_cal_config(self, lawyer_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the Cal.com configuration for a lawyer."""
        try:
            query = self._supabase.table("lawyer_profiles").select("cal_event_type_id, cal_api_key, expertise_domains, specialization_label, availability_status, last_seen_at").eq("lawyer_id", lawyer_id)
            resp = self._supabase.execute_query(query)
            if resp.data:
                return resp.data[0]
            return None
        except Exception as exc:
            logger.error(f"❌ get_lawyer_cal_config failed | {lawyer_id} | {exc}")
            return None

    def update_lawyer_cal_config(self, lawyer_id: str, event_type_id: str, api_key: str) -> bool:
        """Update the Cal.com configuration for a lawyer."""
        try:
            query = self._supabase.table("lawyer_profiles").update({
                "cal_event_type_id": event_type_id,
                "cal_api_key": api_key,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("lawyer_id", lawyer_id)
            self._supabase.execute_query(query)
            logger.info(f"[OK] Updated Cal.com config for lawyer | {lawyer_id}")
            return True
        except Exception as exc:
            logger.error(f"[ERROR] update_lawyer_cal_config failed | {lawyer_id} | {exc}")
            return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _get_clerk_user_details(self, clerk_user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch user details from Clerk API."""
        if not settings.CLERK_SECRET_KEY or not clerk_user_id:
            return None
        try:
            clerk_url = f"https://api.clerk.com/v1/users/{clerk_user_id}"
            resp = httpx.get(clerk_url, headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"})
            if resp.status_code == 200:
                data = resp.json()
                first_name = data.get("first_name") or ""
                last_name = data.get("last_name") or ""
                email_addresses = data.get("email_addresses", [])
                email = email_addresses[0].get("email_address") if email_addresses else None
                return {
                    "full_name": f"{first_name} {last_name}".strip() or data.get("username"),
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name
                }
        except Exception as exc:
            logger.error(f"❌ Failed to fetch Clerk details for {clerk_user_id} | {exc}")
        return None


    def _sync_clerk_role(self, clerk_user_id: str, role: str) -> None:
        """Backward compatible wrapper for _sync_clerk_metadata."""
        self._sync_clerk_metadata(clerk_user_id, {"role": role})

    def _sync_clerk_metadata(self, clerk_user_id: str, metadata: Dict[str, Any]) -> None:
        """Updates the publicMetadata in Clerk with flexible keys."""
        if not settings.CLERK_SECRET_KEY or not clerk_user_id:
            return
        try:
            url = f"https://api.clerk.com/v1/users/{clerk_user_id}/metadata"
            payload = {"public_metadata": metadata}
            headers = {"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}", "Content-Type": "application/json"}
            
            resp = httpx.patch(url, json=payload, headers=headers)
            if resp.status_code == 200:
                logger.info(f"🔑 Clerk metadata synced | {clerk_user_id} → {metadata}")
            else:
                logger.warning(f"⚠️ Clerk metadata sync failed | {clerk_user_id} | status={resp.status_code} | {resp.text}")
        except Exception as exc:
            logger.error(f"❌ Clerk metadata sync error | {clerk_user_id} | {exc}")

    def _log_audit(self, action: str, performer_id: Optional[str], payload: Dict[str, Any]) -> None:
        """Saves an entry to the audit_logs table."""
        try:
            self._supabase.table("audit_logs").insert({
                "action": action,
                "performer_id": performer_id,
                "payload": payload,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
        except Exception as exc:
            logger.warning(f"⚠️ Audit logging failed | {action} | {exc}")

    def get_audit_logs(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Fetches global audit logs for administrative oversight.
        Returns logs sorted by newest first.
        """
        try:
            response = self._supabase.table("audit_logs") \
                .select("*, users!audit_logs_performer_id_fkey(user_name, email)") \
                .order("created_at", desc=True) \
                .range(offset, offset + limit - 1) \
                .execute()
            
            return response.data or []
        except Exception as exc:
            logger.error(f"❌ Failed to fetch audit logs | {exc}")
            return []

    def get_invitations(self) -> List[Dict[str, Any]]:
        """
        Fetches all role invitations for admin tracking.
        Returns invitations sorted by newest first.
        """
        try:
            response = self._supabase.table("role_invites") \
                .select("*") \
                .order("created_at", desc=True) \
                .execute()
            return response.data or []
        except Exception as exc:
            logger.error(f"❌ Failed to fetch invitations | {exc}")
            return []

    def get_all_users_with_profiles(self) -> List[Dict[str, Any]]:
        """Fetch all users joined with user_profiles and lawyer_profiles."""
        response = (
            self._supabase.table("users")
            .select(
                "*, user_profiles(display_name), "
                "lawyer_profiles!lawyer_profiles_lawyer_id_fkey("
                "expertise_domains, specialization_label, availability_status, last_seen_at)"
            )
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []

    def demote_user(self, user_id: str) -> bool:
        """Demotes a user/lawyer back to role 'user'."""
        user_info = self.get_user_by_id(user_id)
        if not user_info:
            return False
        self._supabase.table("users").update({"role": "user"}).eq("user_id", user_id).execute()
        self._sync_clerk_role(user_info["clerk_user_id"], "user")
        return True

    def get_all_lawyers_with_cal(self) -> List[Dict[str, Any]]:
        """Fetch list of all lawyers with their Cal.com setup status."""
        resp = (
            self._supabase.table("users")
            .select(
                "user_id, email, user_name, role, "
                "user_profiles(display_name), "
                "lawyer_profiles!inner(cal_event_type_id, cal_api_key, verification_status, expertise_domains, specialization_label)"
            )
            .order("created_at", desc=False)
            .execute()
        )
        lawyers = []
        for u in (resp.data or []):
            profile = u.get("user_profiles") or {}
            lp = u.get("lawyer_profiles") or {}
            lawyers.append({
                "user_id": u["user_id"],
                "email": u.get("email"),
                "display_name": profile.get("display_name") or u.get("user_name"),
                "cal_configured": bool(lp.get("cal_api_key") and lp.get("cal_event_type_id")),
                "expertise_domains": lp.get("expertise_domains") or [],
                "specialization_label": lp.get("specialization_label"),
            })
        return lawyers

    def update_lawyer_cal_credentials(self, lawyer_id: str, cal_api_key: str, cal_event_type_id: str) -> bool:
        """Update Cal.com credentials for a specific lawyer."""
        resp = (
            self._supabase.table("lawyer_profiles")
            .update({
                "cal_api_key": cal_api_key,
                "cal_event_type_id": cal_event_type_id,
            })
            .eq("lawyer_id", lawyer_id)
            .execute()
        )
        return bool(resp.data)

    def update_lawyer_specialization(self, lawyer_id: str, expertise_domains: List[str], specialization_label: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Update expertise domains and specialization label for a lawyer profile."""
        resp = (
            self._supabase.table("lawyer_profiles")
            .update({
                "expertise_domains": expertise_domains,
                "specialization_label": specialization_label,
            })
            .eq("lawyer_id", lawyer_id)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def get_lawyer_email_and_name(self, lawyer_id: str) -> Optional[Dict[str, str]]:
        """Utility to fetch email and display name for a lawyer."""
        lawyer_user_resp = (
            self._supabase.table("users")
            .select("email, user_profiles(display_name)")
            .eq("user_id", lawyer_id)
            .execute()
        )
        if lawyer_user_resp.data:
            lawyer_user = lawyer_user_resp.data[0]
            lawyer_email = lawyer_user.get("email")
            lawyer_profile = lawyer_user.get("user_profiles") or {}
            lawyer_name = lawyer_profile.get("display_name") or (lawyer_email.split("@")[0] if lawyer_email else "Lawyer")
            return {"email": lawyer_email, "name": lawyer_name}
        return None

    def get_domain_analytics(self) -> Dict[str, Any]:
        """Calculates domain query distribution analytics across assistant messages."""
        from config_domains import DOMAINS_CANONICAL
        DOMAIN_DISPLAY_NAMES = {
            "arbeidsrett": "Employment Law (Arbeidsrett)",
            "arsregnskap_og_selskapsrapportering": "Financial Statements & Reporting (Årsregnskap og Selskapsrapportering)",
            "avtalerett": "Contract Law (Avtalerett)",
            "inkasso_og_tvangsfullbyrdelse": "Debt Collection & Enforcement (Inkasso og Tvangsfullbyrdelse)",
            "konkursrett_og_insolvens": "Bankruptcy & Insolvency (Konkursrett og Insolvens)",
            "manda_fusjon_fisjon": "M&A, Mergers & Acquisitions (M&A, Fusjon, Fisjon)",
            "obligasjonsrett": "Law of Obligations (Obligasjonsrett)",
            "panterett_og_sikkerhetsrett": "Liens & Security Rights (Panterett og Sikkerhetsrett)",
            "pengekravsrett_fordringer": "Monetary Claims & Debt (Pengekravsrett og Fordringer)",
            "personvern_gdpr_business_compliance": "Privacy & GDPR Compliance (Personvern, GDPR & Compliance)",
            "selskapsrett": "Company Law (Selskapsrett)",
            "tvistelosning_smb": "Dispute Resolution for SMBs (Tvisteløsning, SMB)",
            "straffeloven": "Criminal Law (Straffeloven)",
            "strafferett": "Criminal Law (Strafferett)",
            "familierett": "Family Law (Familierett)",
            "arverett": "Inheritance Law (Arverett)",
            "skatterett": "Tax Law (Skatterett)",
            "utlendingsrett": "Immigration Law (Utlendingsrett)",
            "forvaltningsrett": "Administrative Law (Forvaltningsrett)",
            "tingsrett": "Property Law (Tingsrett)",
            "erstatningsrett": "Tort Law (Erstatningsrett)",
            "immaterialrett": "Intellectual Property Law (Immaterialrett)",
            "entrepriserett": "Construction Law (Entrepriserett)",
            "miljorett": "Environmental Law (Miljørett)",
        }

        resp = (
            self._supabase.table("messages")
            .select("metadata")
            .eq("role", "assistant")
            .execute()
        )

        counts = {}
        total = 0
        for msg in (resp.data or []):
            meta = msg.get("metadata") or {}
            domain = meta.get("detected_domain")
            if domain:
                counts[domain] = counts.get(domain, 0) + 1
                total += 1

        distribution = []
        for domain, count in counts.items():
            lower_domain = domain.lower()
            if lower_domain in DOMAIN_DISPLAY_NAMES:
                display_name = DOMAIN_DISPLAY_NAMES[lower_domain]
            else:
                display_name = lower_domain.replace("_", " ").title()
                display_name = f"{display_name} ({domain})"

            distribution.append({
                "name": display_name,
                "raw_key": lower_domain,
                "is_canonical": lower_domain in DOMAINS_CANONICAL,
                "queries": count,
                "percentage": round((count / total) * 100, 1) if total > 0 else 0
            })

        distribution.sort(key=lambda x: x["queries"], reverse=True)
        return {"total": total, "distribution": distribution}

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        """Fetches stored stripe_customer_id for a user from the users table."""
        try:
            resp = self._supabase.table("users").select("stripe_customer_id").eq("user_id", user_id).limit(1).execute()
            if resp.data and len(resp.data) > 0:
                return resp.data[0].get("stripe_customer_id")
        except Exception as exc:
            logger.warning(f"⚠️ Could not fetch stripe_customer_id for user {user_id}: {exc}")
        return None

    def set_stripe_customer_id(self, user_id: str, customer_id: str) -> bool:
        """Stores stripe_customer_id on the user row for future lookups."""
        try:
            resp = self._supabase.table("users").update({"stripe_customer_id": customer_id}).eq("user_id", user_id).execute()
            return bool(resp.data)
        except Exception as exc:
            logger.warning(f"⚠️ Failed to update stripe_customer_id for user {user_id}: {exc}")
            return False

    def get_lawyer_cal_credentials(self, lawyer_id: str) -> Optional[Dict[str, Any]]:
        """Fetches cal_api_key and cal_event_type_id for a lawyer from lawyer_profiles table."""
        try:
            resp = (
                self._supabase.table("lawyer_profiles")
                .select("cal_api_key, cal_event_type_id")
                .eq("lawyer_id", lawyer_id)
                .limit(1)
                .execute()
            )
            if resp.data and len(resp.data) > 0:
                return resp.data[0]
        except Exception as exc:
            logger.error(f"❌ Failed to fetch Cal.com credentials for lawyer {lawyer_id}: {exc}")
        return None

    def get_user_profile_for_booking(self, user_id: str) -> Dict[str, str]:
        """Fetches email and display name for a user for booking creation."""
        try:
            resp = (
                self._supabase.table("users")
                .select("email, user_name, user_profiles(display_name)")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if resp.data and len(resp.data) > 0:
                user_data = resp.data[0]
                profile = user_data.get("user_profiles") or {}
                display_name = profile.get("display_name") or user_data.get("user_name") or "User"
                email = user_data.get("email") or ""
                return {"user_name": display_name, "email": email}
        except Exception as exc:
            logger.error(f"❌ Failed to fetch user profile for booking | user={user_id} | {exc}")
        return {"user_name": "User", "email": ""}

    def get_user_role(self, clerk_user_id: str) -> str:
        """Resolves user role by clerk_user_id from the database."""
        try:
            resp = self._supabase.table("users").select("role").eq("clerk_user_id", clerk_user_id).single().execute()
            if resp.data:
                return resp.data.get("role", "user")
        except Exception as exc:
            logger.warning(f"⚠️ get_user_role failed for clerk_id={clerk_user_id}: {exc}")
        return "user"


