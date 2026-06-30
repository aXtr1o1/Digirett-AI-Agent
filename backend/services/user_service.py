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
from uuid import uuid4
from functools import lru_cache
from config import settings

from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


class UserService:

    def __init__(self, supabase_client: SupabaseClient) -> None:
        self._supabase = supabase_client
        logger.info("✅ UserService initialized")

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
                f"✅ Created user | user_id={user_id} | "
                f"clerk_id={clerk_user_id} | email={email} | role={assigned_role}"
            )
            return user_row

        except Exception as exc:
            logger.error(
                f"❌ create_user_from_webhook failed | clerk_id={clerk_user_id} | {exc}",
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
            logger.error(f"❌ get_user_by_clerk_id failed | {exc}")
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
            logger.error(f"❌ get_user_by_id failed | {exc}")
            return None

    @lru_cache(maxsize=1000)
    def get_user_id_from_clerk_id(self, clerk_user_id: str, email: str = None) -> Optional[str]:
        """
        Quick lookup: Clerk user ID -> Supabase user_id.
        Auto-creates the user in Supabase if missing.
        """
        logger.info(f"🔍 DEBUG: get_user_id_from_clerk_id | clerk_id={clerk_user_id} | provided_email={email}")
        user = self.get_user_by_clerk_id(clerk_user_id)
        if user:
            logger.info(f"✅ Found existing user: {user['user_id']}")
            return user["user_id"]

        logger.info(f"⚡ User {clerk_user_id} not found in Supabase. Attempting auto-creation...")
        # If user not found, auto-create them (fallback for missing webhook)
        try:
            real_email = email
            display_name = None
            
            # If no email provided, try to fetch from Clerk API
            if not real_email and settings.CLERK_SECRET_KEY:
                logger.info(f"🌐 Fetching email from Clerk API for {clerk_user_id}...")
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
                                logger.info(f"📧 Fetched email: {real_email}")
                            
                            username = data.get("username")
                            display_name = username
                        else:
                            logger.error(f"❌ Clerk API returned {resp.status_code}: {resp.text}")
                except Exception as e:
                    logger.error(f"❌ Clerk API request failed: {e}")

            fallback_email = real_email or f"{clerk_user_id}@placeholder.com"
            logger.info(f"🚀 Calling create_user_from_webhook with email: {fallback_email}")
            
            # Final check: Does this email already exist?
            try:
                existing_email_resp = self._supabase.table("users").select("user_id, clerk_user_id").eq("email", fallback_email).execute()
                if existing_email_resp.data:
                    existing = existing_email_resp.data[0]
                    logger.error(f"🚨 EMAIL CONFLICT: Email {fallback_email} is already used by Supabase user {existing['user_id']} (Clerk ID: {existing['clerk_user_id']})")
                    # Optionally: Update the clerk_user_id if it's the same person but different Clerk instance? 
                    # For now, just return the existing ID to unblock them, or fail clearly.
                    return existing["user_id"]
            except Exception as e:
                logger.warning(f"⚠️ Email uniqueness check failed (non-fatal): {e}")

            new_user = self.create_user_from_webhook(
                clerk_user_id=clerk_user_id,
                email=fallback_email,
                tenant_id=None,
                display_name=display_name,
                username=display_name # we set username to display_name in fallback
            )
            logger.info(f"🎉 Successfully auto-created user: {new_user.get('user_id')}")
            return new_user.get("user_id")
        except Exception as exc:
            logger.error(f"❌ FATAL: Auto-creation failed for {clerk_user_id} | {exc}", exc_info=True)

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

            logger.info(f"✅ Updated role | user_id={user_id} → {new_role}")
            return True
        except Exception as exc:
            logger.error(f"❌ update_role failed | user_id={user_id} | {exc}")
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

            logger.info(f"✅ Suspended user | user_id={user_id}")
            return True
        except Exception as exc:
            logger.error(f"❌ suspend_user failed | {exc}")
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

            logger.info(f"✅ Reactivated user | user_id={user_id}")
            return True
        except Exception as exc:
            logger.error(f"❌ reactivate_user failed | {exc}")
            return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ROLE MANAGEMENT (PHASE 2)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def accept_invite(self, token: str, clerk_user_id: str, email: str) -> bool:
        """
        Accepts a pending invitation. Validates the token and email, 
        promotes the user, and marks the invite as accepted.
        """
        try:
            # 1. Look up the invite
            resp = self._supabase.table("role_invites").select("*").eq("token", token).eq("status", "pending").execute()
            if not resp.data:
                logger.warning(f"⚠️ Invalid or expired invite token: {token}")
                return False
                
            invite = resp.data[0]
            
            # 3. Get user_id from clerk_id
            user_id = self.get_user_id_from_clerk_id(clerk_user_id)
            if not user_id:
                logger.error(f"❌ Could not find internal user_id for clerk_id: {clerk_user_id}")
                return False
                
            user_info = self.get_user_by_id(user_id)
            if not user_info:
                logger.error(f"❌ Could not find user info for user_id: {user_id}")
                return False
                
            db_email = user_info.get("email")
            
            # 2. Validate email matches
            invite_email = invite.get("email")
            
            if not invite_email or not db_email:
                logger.warning(f"⚠️ Missing email for verification. Token email: {invite_email}, DB email: {db_email}")
                return False
                
            if invite_email.lower() != db_email.lower():
                logger.warning(f"⚠️ Invite email mismatch. Token email: {invite_email}, DB email: {db_email}")
                return False
                
            role = invite["role"]
            current_role = user_info.get("role", "user")

            if role == "lawyer":
                if current_role == "admin":
                    # DUAL ROLE SCENARIO: Keep as Admin, just add Lawyer profile
                    logger.info(f"🛡️ Dual-role detected for Admin {user_id}. Creating lawyer profile...")
                    success = self.enable_lawyer_dashboard_for_admin(user_id=user_id, admin_id=user_id)
                else:
                    success = self.promote_to_lawyer(user_id=user_id, admin_id=None, bar_license="PENDING", bar_council="PENDING")
            elif role == "admin":
                full_name = user_info.get("user_name") if user_info else "Admin"
                success = self.promote_to_admin(user_id=user_id, admin_id="system", full_name=full_name)
            elif role == "system_admin":
                success = self.promote_to_system_admin(user_id=user_id, admin_id="system")
                
            if not success:
                return False
                
            # 5. Mark invite as accepted
            self._supabase.table("role_invites").update({"status": "accepted"}).eq("invite_id", invite["invite_id"]).execute()
            
            # 6. Audit log
            self._log_audit("user.invite_accepted", user_id, {"role": role, "invite_id": invite["invite_id"]})
            
            logger.info(f"✅ Invite accepted for {email} -> {role}")
            return True
            
        except Exception as exc:
            logger.error(f"❌ accept_invite failed | {exc}")
            return False

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
                    logger.warning(f"⚠️ User {email} already has role {existing_role}. Invitation blocked.")
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
            self._supabase.table("role_invites").upsert(invite_data, on_conflict="email").execute()
            
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
            resp = self._supabase.table("role_invites").select("*").order("created_at", desc=True).execute()
            return resp.data or []
        except Exception as exc:
            logger.error(f"❌ get_all_invitations failed | {exc}")
            return []

    def revoke_invitation(self, invite_id: str) -> bool:
        """
        Deletes a pending invitation from the role_invites table.
        """
        try:
            resp = self._supabase.table("role_invites").delete().eq("invite_id", invite_id).execute()
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
            resp = self._supabase.table("lawyer_profiles").select("cal_event_type_id, cal_api_key, expertise_domains, specialization_label, availability_status, last_seen_at").eq("lawyer_id", lawyer_id).execute()
            if resp.data:
                return resp.data[0]
            return None
        except Exception as exc:
            logger.error(f"❌ get_lawyer_cal_config failed | {lawyer_id} | {exc}")
            return None

    def update_lawyer_cal_config(self, lawyer_id: str, event_type_id: str, api_key: str) -> bool:
        """Update the Cal.com configuration for a lawyer."""
        try:
            self._supabase.table("lawyer_profiles").update({
                "cal_event_type_id": event_type_id,
                "cal_api_key": api_key,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("lawyer_id", lawyer_id).execute()
            logger.info(f"✅ Updated Cal.com config for lawyer | {lawyer_id}")
            return True
        except Exception as exc:
            logger.error(f"❌ update_lawyer_cal_config failed | {lawyer_id} | {exc}")
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