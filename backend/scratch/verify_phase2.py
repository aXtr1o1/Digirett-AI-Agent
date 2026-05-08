"""
verify_phase2.py
================
Comprehensive verification for Phase 2: RBAC + HITL

Usage:
  # Run all tests (mocked email):
  python backend/scratch/verify_phase2.py

  # Send a REAL invitation email (requires RESEND_API_KEY in .env):
  python backend/scratch/verify_phase2.py --send-invite your@email.com lawyer
"""

import sys
import os
import uuid
import asyncio

# Add backend to path and change CWD so .env is found
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)
os.chdir(backend_dir)

from config import settings
from db.supabase_client import get_supabase
from services.user_service import UserService
from services.email_service import EmailService
from services.hitl_service import HitlService

# ─────────────────────────────────────────────────────────────
PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"
INFO = "[INFO]"
# ─────────────────────────────────────────────────────────────


def section(title: str):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")


async def run_verification(send_invite_to: str = None, invite_role: str = "lawyer"):

    # ── Setup ────────────────────────────────────────────────
    supabase = get_supabase()
    supabase.connect(url=settings.SUPABASE_URL, key=settings.SUPABASE_KEY)

    user_service = UserService(supabase)
    hitl_service = HitlService(supabase)
    admin_id = settings.DEFAULT_USER_ID

    # ─────────────────────────────────────────────────────────
    # SECTION 1 — Invitation Flow (Lawyer)
    # ─────────────────────────────────────────────────────────
    section("1. Invitation Flow")

    if send_invite_to:
        # Use REAL Resend to send an actual invitation email
        print(f"{INFO} Sending REAL invitation to {send_invite_to} as {invite_role}...")
        email_service = EmailService(
            api_key=settings.RESEND_API_KEY,
            from_email=settings.INVITE_FROM_EMAIL,
        )
        test_email = send_invite_to
        success = user_service.invite_user(test_email, invite_role, admin_id, email_service)
        if success:
            print(f"{PASS} Real invitation email sent to {test_email}")
            print(f"{INFO} Check your inbox, click the link, sign up, and watch the role auto-assign!")
            print(f"\n  Invite flow:")
            print(f"  1. You click the link in the email")
            print(f"  2. You sign up / sign in via Clerk")
            print(f"  3. Clerk fires the 'user.created' webhook")
            print(f"  4. Backend checks role_invites for your email")
            print(f"  5. Role is auto-set to '{invite_role}' in users table")
            print(f"  6. A {invite_role}_profiles row is created")
            print(f"  7. Clerk publicMetadata.role is updated to '{invite_role}'")
        else:
            print(f"{FAIL} Failed to send invitation. Check RESEND_API_KEY in .env")
        return  # Only do the invite when explicitly requested
    else:
        # Mocked test email
        email_service = EmailService(api_key="mock_key", from_email="test@digirett.no")
        email_service.send_invitation_email = lambda e, r, t: True
        test_email = f"test_{invite_role}_{uuid.uuid4().hex[:6]}@example.com"

        success = user_service.invite_user(test_email, "lawyer", admin_id, email_service)
        if success:
            print(f"{PASS} role_invites row created for {test_email}")
        else:
            print(f"{FAIL} Failed to create invitation")
            return

    # ─────────────────────────────────────────────────────────
    # SECTION 2 — Webhook Auto-Provisioning -> Lawyer
    # ─────────────────────────────────────────────────────────
    section("2. Webhook Auto-Provisioning -> Lawyer")

    clerk_id = f"user_test_{uuid.uuid4().hex[:8]}"
    user = user_service.create_user_from_webhook(
        clerk_user_id=clerk_id,
        email=test_email,
        tenant_id=None,
        display_name="Test Lawyer User"
    )

    # Role check
    if user["role"] == "lawyer":
        print(f"{PASS} users.role = 'lawyer'  (auto-assigned from invite)")
    else:
        print(f"{FAIL} users.role = '{user['role']}', expected 'lawyer'")

    # user_profiles row
    up_resp = supabase.table("user_profiles").select("*").eq("user_id", user["user_id"]).execute()
    if up_resp.data:
        print(f"{PASS} user_profiles row created | display_name='{up_resp.data[0].get('display_name')}'")
    else:
        print(f"{FAIL} user_profiles row MISSING")

    # lawyer_profiles row
    lp_resp = supabase.table("lawyer_profiles").select("*").eq("lawyer_id", user["user_id"]).execute()
    if lp_resp.data:
        lp = lp_resp.data[0]
        print(f"{PASS} lawyer_profiles row created | verification_status='{lp.get('verification_status')}'")
    else:
        print(f"{FAIL} lawyer_profiles row MISSING")

    lawyer_user = user

    # ─────────────────────────────────────────────────────────
    # SECTION 3 — Admin Promotion + admin_profiles
    # ─────────────────────────────────────────────────────────
    section("3. Admin Promotion + admin_profiles")

    admin_test_email = f"test_admin_{uuid.uuid4().hex[:6]}@example.com"
    # Create a plain user first
    plain_user = user_service.create_user_from_webhook(
        clerk_user_id=f"user_test_{uuid.uuid4().hex[:8]}",
        email=admin_test_email,
        tenant_id=None,
        display_name="Promoted Admin User"
    )
    print(f"{INFO} Created plain user: {plain_user['user_id']} | role={plain_user['role']}")

    # Promote to admin
    promoted = user_service.promote_to_admin(
        user_id=plain_user["user_id"],
        admin_id=admin_id,
        full_name="Test Admin Full Name"
    )
    if promoted:
        print(f"{PASS} promote_to_admin() succeeded")
    else:
        print(f"{FAIL} promote_to_admin() failed")

    # Verify role in users table
    user_row = supabase.table("users").select("role").eq("user_id", plain_user["user_id"]).execute()
    if user_row.data and user_row.data[0]["role"] == "admin":
        print(f"{PASS} users.role updated to 'admin'")
    else:
        print(f"{FAIL} users.role NOT updated (got {user_row.data})")

    # Verify admin_profiles row
    ap_resp = supabase.table("admin_profiles").select("*").eq("admin_id", plain_user["user_id"]).execute()
    if ap_resp.data:
        ap = ap_resp.data[0]
        print(f"{PASS} admin_profiles row created | full_name='{ap.get('full_name')}'")
    else:
        print(f"{FAIL} admin_profiles row MISSING")

    # ─────────────────────────────────────────────────────────
    # SECTION 4 — Lawyer Promotion (from existing user)
    # ─────────────────────────────────────────────────────────
    section("4. Lawyer Promotion (promote_to_lawyer)")

    lawyer_test_email = f"test_promote_{uuid.uuid4().hex[:6]}@example.com"
    plain_user2 = user_service.create_user_from_webhook(
        clerk_user_id=f"user_test_{uuid.uuid4().hex[:8]}",
        email=lawyer_test_email,
        tenant_id=None,
        display_name="Promoted Lawyer User"
    )

    promoted2 = user_service.promote_to_lawyer(
        user_id=plain_user2["user_id"],
        admin_id=admin_id,
        bar_license="BAR-TEST-001",
        bar_council="Oslo Bar Council"
    )
    if promoted2:
        print(f"{PASS} promote_to_lawyer() succeeded")
    else:
        print(f"{FAIL} promote_to_lawyer() failed")

    lp_resp2 = supabase.table("lawyer_profiles").select("*").eq("lawyer_id", plain_user2["user_id"]).execute()
    if lp_resp2.data:
        lp2 = lp_resp2.data[0]
        print(f"{PASS} lawyer_profiles row created | bar_license='{lp2.get('bar_license_number')}' | council='{lp2.get('bar_council')}'")
    else:
        print(f"{FAIL} lawyer_profiles row MISSING")

    # ─────────────────────────────────────────────────────────
    # SECTION 5 — HITL Escalation (no tenant)
    # ─────────────────────────────────────────────────────────
    section("5. HITL Escalation Lifecycle")

    conv_resp = supabase.table("conversations").select("conversation_id").limit(1).execute()
    if not conv_resp.data:
        print(f"{SKIP} No conversations in DB — skipping HITL test")
    else:
        conv_id = conv_resp.data[0]["conversation_id"]
        msg_resp = supabase.table("messages").select("message_id").eq("conversation_id", conv_id).limit(1).execute()
        if not msg_resp.data:
            print(f"{SKIP} No messages in that conversation — skipping HITL test")
        else:
            msg_id = msg_resp.data[0]["message_id"]

            ticket = hitl_service.create_ticket(
                conversation_id=conv_id,
                user_id=lawyer_user["user_id"],
                trigger_message_id=msg_id,
                user_note="Test escalation note"
            )
            print(f"{PASS} Ticket created | id={ticket['ticket_id']}")

            # Assign
            ok = hitl_service.assign_ticket(ticket["ticket_id"], lawyer_user["user_id"])
            print(f"{PASS if ok else FAIL} Ticket assigned to lawyer")

            # Verify ticket state
            t_resp = supabase.table("hitl_tickets").select("*").eq("ticket_id", ticket["ticket_id"]).execute()
            if t_resp.data:
                t = t_resp.data[0]
                print(f"{PASS} Ticket DB state | status='{t['status']}' | assigned_lawyer_id='{t.get('assigned_lawyer_id')}'")

            # Respond
            ok2 = hitl_service.respond_to_ticket(ticket["ticket_id"], lawyer_user["user_id"], "Here is the lawyer's answer.")
            print(f"{PASS if ok2 else FAIL} Ticket response saved and resolved")

    # ─────────────────────────────────────────────────────────
    # SECTION 6 — Audit Logs
    # ─────────────────────────────────────────────────────────
    section("6. Audit Logs")

    audit_resp = supabase.table("audit_logs").select("action, performer_id, created_at").order("created_at", desc=True).limit(5).execute()
    if audit_resp.data:
        print(f"{PASS} Last {len(audit_resp.data)} audit entries:")
        for entry in audit_resp.data:
            print(f"       action='{entry['action']}' | performer='{entry.get('performer_id', 'N/A')}'")
    else:
        print(f"{FAIL} No audit log entries found")

    print(f"\n{'='*55}")
    print(f"  Verification Complete!")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    # Check if --send-invite mode
    if "--send-invite" in sys.argv:
        idx = sys.argv.index("--send-invite")
        target_email = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        role = sys.argv[idx + 2] if idx + 2 < len(sys.argv) else "lawyer"
        if not target_email:
            print("Usage: python verify_phase2.py --send-invite <email> <role>")
            sys.exit(1)
        asyncio.run(run_verification(send_invite_to=target_email, invite_role=role))
    else:
        asyncio.run(run_verification())
