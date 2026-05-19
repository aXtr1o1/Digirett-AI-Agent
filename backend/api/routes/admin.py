"""
api/routes/admin.py — Admin management endpoints

Existing endpoints (unchanged):
  POST /admin/invite
  GET  /admin/users
  GET  /admin/audit-logs
  POST /admin/promote/lawyer
  POST /admin/promote/admin
  PATCH /admin/users/{user_id}/demote
  PATCH /admin/users/{user_id}/suspend

New endpoints (HITL case management):
  GET   /admin/tickets                              — Full case queue (all statuses)
  PATCH /admin/tickets/{ticket_id}/assign/{lawyer_id} — Force-assign any ticket
  PATCH /admin/tickets/{ticket_id}/unassign         — Remove lawyer, reset to open
  PATCH /admin/tickets/{ticket_id}/close            — Close ticket with optional notes
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, EmailStr

from core.auth import ClerkUser, require_db_role
from services.email_service import EmailService
from services.hitl_service import HitlService
from services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

# ── Services ─────────────────────────────────────────────────────────
_user_service: Optional[UserService] = None
_email_service: Optional[EmailService] = None
_hitl_service: Optional[HitlService] = None


def set_services(
    user_svc: UserService,
    email_svc: EmailService,
    hitl_svc: Optional[HitlService] = None,
) -> None:
    global _user_service, _email_service, _hitl_service
    _user_service = user_svc
    _email_service = email_svc
    _hitl_service = hitl_svc


# ── Schemas ──────────────────────────────────────────────────────────

class InviteRequest(BaseModel):
    email: EmailStr
    role: str  # 'lawyer' | 'admin'


class PromoteLawyerRequest(BaseModel):
    user_id: str
    bar_license: Optional[str] = None
    bar_council: Optional[str] = None


class PromoteAdminRequest(BaseModel):
    user_id: str
    full_name: Optional[str] = None


class AdminCloseTicketRequest(BaseModel):
    outcome_notes: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER MANAGEMENT (existing)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/invite", summary="Invite a new lawyer or admin via email")
async def invite_user(
    req: InviteRequest,
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    if req.role not in ["lawyer", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'lawyer' or 'admin'.")

    admin_id = _user_service.get_user_id_from_clerk_id(current_admin.clerk_user_id)
    admin_email = current_admin.email

    try:
        success = await _user_service.invite_user(
            email=req.email,
            role=req.role,
            admin_id=admin_id,
            email_service=_email_service,
            admin_email=admin_email,
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to send invitation.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": f"Invitation sent to {req.email}"}


@router.get("/invitations", summary="List all pending/active role invitations")
async def list_invitations(
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    """
    Fetches all invitation records from the role_invites table.
    """
    invites = _user_service.get_all_invitations()
    return invites


@router.delete("/invitations/{invite_id}", summary="Revoke a sent invitation")
async def revoke_invitation(
    invite_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    """
    Deletes a pending invitation record from the database.
    """
    success = _user_service.revoke_invitation(invite_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or already accepted.",
        )
    return {"message": "Invitation revoked successfully."}


@router.get("/users", summary="List all users in the system")
async def list_users(
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    try:
        response = (
            _user_service._supabase.table("users")
            .select("*, user_profiles(display_name)")
            .order("created_at", desc=True)
            .execute()
        )
        return response.data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/audit-logs", summary="Fetch global audit logs")
async def get_audit_logs(
    limit: int = 50,
    offset: int = 0,
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    logs = _user_service.get_audit_logs(limit=limit, offset=offset)
    return logs


@router.post("/promote/lawyer", summary="Promote a user to Lawyer role")
async def promote_to_lawyer(
    req: PromoteLawyerRequest,
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    admin_id = _user_service.get_user_id_from_clerk_id(current_admin.clerk_user_id)
    success = await _user_service.promote_to_lawyer(
        user_id=req.user_id,
        admin_id=admin_id,
        bar_license=req.bar_license,
        bar_council=req.bar_council,
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to promote user to lawyer.")
    return {"message": "User promoted to lawyer successfully."}


@router.post("/promote/admin", summary="Promote a user to Admin role")
async def promote_to_admin(
    req: PromoteAdminRequest,
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    admin_id = _user_service.get_user_id_from_clerk_id(current_admin.clerk_user_id)
    success = await _user_service.promote_to_admin(
        user_id=req.user_id,
        admin_id=admin_id,
        full_name=req.full_name,
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to promote user to admin.")
    return {"message": "User promoted to admin successfully."}


@router.patch("/users/{user_id}/demote", summary="Demote a lawyer back to user")
async def admin_demote_user(
    user_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    try:
        user_info = _user_service.get_user_by_id(user_id)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        _user_service._supabase.table("users").update({"role": "user"}).eq("user_id", user_id).execute()
        _user_service._sync_clerk_role(user_info["clerk_user_id"], "user")
        return {"status": "success", "message": "User demoted to standard user."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/users/{user_id}/suspend", summary="Suspend a user account")
async def admin_suspend_user(
    user_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    try:
        success = _user_service.suspend_user(user_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to suspend user and sync to Clerk.")
        return {"status": "success", "message": "User suspended."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/users/{user_id}/activate", summary="Unsuspend a user account")
async def admin_unsuspend_user(
    user_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    try:
        success = _user_service.reactivate_user(user_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to unsuspend user and sync to Clerk.")
        return {"status": "success", "message": "User suspension revoked."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CASE QUEUE MANAGEMENT (new — Phase 5)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/tickets",
    summary="Admin view of ALL tickets across all statuses",
)
async def admin_get_all_tickets(
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    """
    Phase 5: Admin sees the full case queue with all statuses:
    open → assigned → booked → resolved → closed

    Each ticket includes:
    - user_display_name, user_email, user_phone_number
    - lawyer_name, lawyer_email (if assigned)
    - conversation_summary (AI-generated case brief)
    - booking_url (Google Meet link, if booked)
    - outcome_notes (if resolved/closed)
    - all timestamps: created_at, assigned_at, booking_confirmed_at, resolved_at, closed_at
    """
    tickets = _hitl_service.get_all_tickets_for_admin()
    return tickets


@router.patch(
    "/tickets/{ticket_id}/assign/{lawyer_id}",
    summary="Admin force-assigns any ticket to a lawyer (Phase 5 override)",
)
async def admin_assign_ticket(
    ticket_id: str,
    lawyer_id: str,
    background_tasks: BackgroundTasks,
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    """
    Phase 5: Admin can force-assign a ticket to any lawyer regardless of
    current status. Works on open, assigned, or booked tickets.

    If the ticket was already booked with a different lawyer, the booking
    fields are cleared (user must re-book with the new lawyer).

    After successful assignment, sends a notification email to the user.
    """
    success = _hitl_service.admin_assign_ticket(ticket_id, lawyer_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found.",
        )

    # Notify user in the background
    background_tasks.add_task(_send_admin_assignment_notification, ticket_id, lawyer_id)

    return {
        "status": "success",
        "message": f"Ticket {ticket_id[:8]} assigned to lawyer {lawyer_id[:8]}.",
    }


async def _send_admin_assignment_notification(ticket_id: str, lawyer_id: str):
    """Internal helper to send email notification after admin assignment."""
    try:
        ticket = _hitl_service.get_ticket_by_id(ticket_id)
        if ticket and _email_service:
            user_email = ticket.get("user_email")
            user_name = ticket.get("user_display_name") or "User"

            lawyer_resp = (
                _hitl_service._supabase.table("users")
                .select("user_name, user_profiles(display_name)")
                .eq("user_id", lawyer_id)
                .limit(1)
                .execute()
            )
            lawyer_name = "Your assigned lawyer"
            if lawyer_resp.data:
                ld = lawyer_resp.data[0]
                lp = ld.get("user_profiles") or {}
                lawyer_name = lp.get("display_name") or ld.get("user_name") or lawyer_name

            if user_email:
                await _email_service.send_lawyer_assigned_email(
                    to_email=user_email,
                    user_name=user_name,
                    lawyer_name=lawyer_name,
                    ticket_id=ticket_id,
                )
    except Exception as notify_exc:
        logger.warning(f"⚠️ Admin assign user notification failed (non-fatal) | {notify_exc}")


@router.patch(
    "/tickets/{ticket_id}/unassign",
    summary="Admin removes lawyer assignment, resets ticket to 'open'",
)
async def admin_unassign_ticket(
    ticket_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    """
    Phase 5: Admin removes the current lawyer from a ticket and resets it
    to 'open' status so any lawyer can claim it again.

    Also clears any booking data (user must re-book if needed).
    """
    success = _hitl_service.admin_unassign_ticket(ticket_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found.",
        )
    return {"status": "success", "message": f"Ticket {ticket_id[:8]} unassigned and returned to queue."}


@router.patch(
    "/tickets/{ticket_id}/close",
    summary="Admin closes a ticket with optional outcome/billing notes",
)
async def admin_close_ticket(
    ticket_id: str,
    req: AdminCloseTicketRequest = AdminCloseTicketRequest(),
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    """
    Phase 8: Admin closes a ticket from any status.
    Optionally stores outcome_notes for billing or case record purposes.
    """
    success = _hitl_service.close_ticket_admin(
        ticket_id=ticket_id,
        outcome_notes=req.outcome_notes,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found.",
        )
    return {"status": "success", "message": f"Ticket {ticket_id[:8]} closed."}


@router.get(
    "/lawyers",
    summary="Admin fetches list of all lawyers (for assignment dropdowns)",
)
async def admin_list_lawyers(
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    """
    Returns all users with role='lawyer' for use in the admin assignment dropdown.
    Includes their Cal.com configuration status.
    """
    try:
        # We fetch all users who HAVE a lawyer profile (!inner join), regardless of their role
        resp = (
            _user_service._supabase.table("users")
            .select(
                "user_id, email, user_name, role, "
                "user_profiles(display_name), "
                "lawyer_profiles!inner(cal_event_type_id, cal_api_key, verification_status)"
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
            })
        return lawyers
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch(
    "/lawyers/{lawyer_id}/cal-credentials",
    summary="Admin sets a lawyer's Cal.com credentials",
)
async def admin_set_lawyer_cal_credentials(
    lawyer_id: str,
    cal_api_key: str,
    cal_event_type_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin")),
):
    """
    Admin sets the Cal.com API key and event type ID for a specific lawyer.
    These are stored in lawyer_profiles and used for slot fetching + booking.

    cal_api_key:        The lawyer's personal Cal.com API key
    cal_event_type_id:  The ID of the lawyer's consultation event type in Cal.com
    """
    try:
        resp = (
            _user_service._supabase.table("lawyer_profiles")
            .update({
                "cal_api_key": cal_api_key,
                "cal_event_type_id": cal_event_type_id,
            })
            .eq("lawyer_id", lawyer_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lawyer profile not found. Ensure the user has been promoted to lawyer.",
            )
        return {"status": "success", "message": "Cal.com credentials saved."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
