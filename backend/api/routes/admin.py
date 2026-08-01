"""
api/routes/admin.py — Admin management endpoints

Refactored according to code review standards:
- FastAPI Dependency Injection for services
- Response Models for Swagger quality and type safety
- Enum / Literal validation for request payload values
- Zero direct database access in route handlers
- Delegated SLA reporting and Domain analytics to service layer
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, EmailStr

from core.auth import ClerkUser, require_db_role
from services.email_service import EmailService
from services.hitl_service import HitlService
from services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


from fastapi import Request

# ── Dependency Injection & Services ───────────────────────────────────
_user_service: Optional[UserService] = None
_email_service: Optional[EmailService] = None
_hitl_service: Optional[HitlService] = None


def set_services(
    user_svc: UserService,
    email_svc: EmailService,
    hitl_svc: Optional[HitlService] = None,
) -> None:
    """Legacy service injector for testing / backwards compatibility."""
    global _user_service, _email_service, _hitl_service
    _user_service = user_svc
    _email_service = email_svc
    _hitl_service = hitl_svc
    if _hitl_service and hasattr(_user_service, "_supabase"):
        _hitl_service._user_svc_supabase = _user_service._supabase


def get_user_service(request: Request) -> UserService:
    svc = getattr(request.app.state, "user_service", None) or _user_service
    if svc is None:
        raise RuntimeError("UserService is not initialized.")
    return svc


def get_email_service(request: Request) -> Optional[EmailService]:
    return getattr(request.app.state, "email_service", None) or _email_service


def get_hitl_service(request: Request) -> HitlService:
    svc = getattr(request.app.state, "hitl_service", None) or _hitl_service
    if svc is None:
        raise RuntimeError("HitlService is not initialized.")
    return svc






# ── Enums ─────────────────────────────────────────────────────────────

class AllowedUserRole(str, Enum):
    USER = "user"
    LAWYER = "lawyer"
    ADMIN = "admin"
    SYSTEM_ADMIN = "system_admin"


# ── Response & Request Pydantic Schemas ──────────────────────────────

class SuccessResponse(BaseModel):
    status: str = "success"
    message: str


class InviteRequest(BaseModel):
    email: EmailStr
    role: AllowedUserRole


class PromoteLawyerRequest(BaseModel):
    user_id: str
    bar_license: Optional[str] = None
    bar_council: Optional[str] = None


class PromoteAdminRequest(BaseModel):
    user_id: str
    full_name: Optional[str] = None


class AdminCloseTicketRequest(BaseModel):
    outcome_notes: Optional[str] = None


class AdminSpecializationRequest(BaseModel):
    expertise_domains: List[str]
    specialization_label: Optional[str] = None


class LawyerSummaryResponse(BaseModel):
    user_id: str
    email: Optional[str] = None
    display_name: str
    cal_configured: bool
    expertise_domains: List[str] = []
    specialization_label: Optional[str] = None


class AverageResponseTimes(BaseModel):
    avg_claim_hours: float
    avg_book_hours: float
    avg_resolve_days: float


class LawyerPerformanceMetric(BaseModel):
    lawyer_id: str
    name: str
    tickets: int
    avg_resolve_days: Optional[float] = None
    rating: Optional[float] = None


class SLAReportResponse(BaseModel):
    active_breaches: List[Dict[str, Any]]
    average_response_times: AverageResponseTimes
    lawyer_performance: List[LawyerPerformanceMetric]


class DomainAnalyticsItem(BaseModel):
    name: str
    raw_key: str
    is_canonical: bool
    queries: int
    percentage: float


class DomainAnalyticsResponse(BaseModel):
    total: int
    distribution: List[DomainAnalyticsItem]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "/invite",
    summary="Invite a new lawyer or admin via email",
    response_model=SuccessResponse,
)
async def invite_user(
    req: InviteRequest,
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
    email_service: Optional[EmailService] = Depends(get_email_service),
):
    admin_id = user_service.get_user_id_from_clerk_id(current_admin.clerk_user_id)
    admin_email = current_admin.email
    if not admin_email:
        admin_user_info = user_service.get_user_by_id(admin_id)
        if admin_user_info:
            admin_email = admin_user_info.get("email")

    try:
        success = await user_service.invite_user(
            email=req.email,
            role=req.role.value,
            admin_id=admin_id,
            email_service=email_service,
            admin_email=admin_email,
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send invitation.")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return SuccessResponse(message=f"Invitation sent to {req.email}")


@router.get(
    "/invitations",
    summary="List all pending/active role invitations",
    response_model=List[Dict[str, Any]],
)
async def list_invitations(
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
):
    """Fetches all invitation records from the role_invites table."""
    return user_service.get_all_invitations()


@router.delete(
    "/invitations/{invite_id}",
    summary="Revoke a sent invitation",
    response_model=SuccessResponse,
)
async def revoke_invitation(
    invite_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
):
    """Deletes a pending invitation record from the database."""
    success = user_service.revoke_invitation(invite_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or already accepted.",
        )
    return SuccessResponse(message="Invitation revoked successfully.")


@router.get(
    "/users",
    summary="List all users in the system",
    response_model=List[Dict[str, Any]],
)
async def list_users(
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
):
    try:
        return user_service.get_all_users_with_profiles()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get(
    "/audit-logs",
    summary="Fetch global audit logs",
    response_model=List[Dict[str, Any]],
)
async def get_audit_logs(
    limit: int = 50,
    offset: int = 0,
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
):
    return user_service.get_audit_logs(limit=limit, offset=offset)


@router.post(
    "/promote/lawyer",
    summary="Promote a user to Lawyer role",
    response_model=SuccessResponse,
)
async def promote_to_lawyer(
    req: PromoteLawyerRequest,
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
):
    admin_id = user_service.get_user_id_from_clerk_id(current_admin.clerk_user_id)
    success = await user_service.promote_to_lawyer(
        user_id=req.user_id,
        admin_id=admin_id,
        bar_license=req.bar_license,
        bar_council=req.bar_council,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to promote user to lawyer.")
    return SuccessResponse(message="User promoted to lawyer successfully.")


@router.post(
    "/promote/admin",
    summary="Promote a user to Admin role",
    response_model=SuccessResponse,
)
async def promote_to_admin(
    req: PromoteAdminRequest,
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
):
    admin_id = user_service.get_user_id_from_clerk_id(current_admin.clerk_user_id)
    success = await user_service.promote_to_admin(
        user_id=req.user_id,
        admin_id=admin_id,
        full_name=req.full_name,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to promote user to admin.")
    return SuccessResponse(message="User promoted to admin successfully.")


@router.patch(
    "/users/{user_id}/demote",
    summary="Demote a lawyer back to user",
    response_model=SuccessResponse,
)
async def admin_demote_user(
    user_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
):
    try:
        user_info = user_service.get_user_by_id(user_id)
        if not user_info:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        # Hierarchy safeguard
        if current_admin.db_role == "system_admin" and user_info.get("role") in ["admin", "system_admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. System Admins cannot demote Admin or System Admin accounts.",
            )

        success = user_service.demote_user(user_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to demote user.")
        return SuccessResponse(message="User demoted to standard user.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.patch(
    "/users/{user_id}/suspend",
    summary="Suspend a user account",
    response_model=SuccessResponse,
)
async def admin_suspend_user(
    user_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
):
    try:
        user_info = user_service.get_user_by_id(user_id)
        if user_info and current_admin.db_role == "system_admin" and user_info.get("role") in ["admin", "system_admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. System Admins cannot suspend Admin or System Admin accounts.",
            )

        success = user_service.suspend_user(user_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to suspend user and sync to Clerk.")
        return SuccessResponse(message="User suspended.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.patch(
    "/users/{user_id}/activate",
    summary="Unsuspend a user account",
    response_model=SuccessResponse,
)
async def admin_unsuspend_user(
    user_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
):
    try:
        user_info = user_service.get_user_by_id(user_id)
        if user_info and current_admin.db_role == "system_admin" and user_info.get("role") in ["admin", "system_admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. System Admins cannot activate Admin or System Admin accounts.",
            )

        success = user_service.reactivate_user(user_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to unsuspend user and sync to Clerk.")
        return SuccessResponse(message="User suspension revoked.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CASE QUEUE MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/tickets",
    summary="Admin view of ALL tickets across all statuses",
    response_model=List[Dict[str, Any]],
)
async def admin_get_all_tickets(
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    hitl_service: HitlService = Depends(get_hitl_service),
):
    return hitl_service.get_all_tickets_for_admin()


@router.patch(
    "/tickets/{ticket_id}/assign/{lawyer_id}",
    summary="Admin force-assigns any ticket to a lawyer",
    response_model=SuccessResponse,
)
async def admin_assign_ticket(
    ticket_id: str,
    lawyer_id: str,
    background_tasks: BackgroundTasks,
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    hitl_service: HitlService = Depends(get_hitl_service),
    email_service: Optional[EmailService] = Depends(get_email_service),
    user_service: UserService = Depends(get_user_service),
):
    success = hitl_service.admin_assign_ticket(ticket_id, lawyer_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found.",
        )

    # Notify user in background via service
    if email_service:
        background_tasks.add_task(
            hitl_service.send_admin_assignment_notification,
            ticket_id=ticket_id,
            lawyer_id=lawyer_id,
            email_service=email_service,
            user_service=user_service,
        )

    return SuccessResponse(message=f"Ticket {ticket_id[:8]} assigned to lawyer {lawyer_id[:8]}.")



@router.patch(
    "/tickets/{ticket_id}/unassign",
    summary="Admin removes lawyer assignment, resets ticket to 'open'",
    response_model=SuccessResponse,
)
async def admin_unassign_ticket(
    ticket_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    hitl_service: HitlService = Depends(get_hitl_service),
):
    success = hitl_service.admin_unassign_ticket(ticket_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found.",
        )
    return SuccessResponse(message=f"Ticket {ticket_id[:8]} unassigned and returned to queue.")


@router.patch(
    "/tickets/{ticket_id}/close",
    summary="Admin closes a ticket with optional outcome/billing notes",
    response_model=SuccessResponse,
)
async def admin_close_ticket(
    ticket_id: str,
    req: AdminCloseTicketRequest = AdminCloseTicketRequest(),
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    hitl_service: HitlService = Depends(get_hitl_service),
):
    success = hitl_service.close_ticket_admin(
        ticket_id=ticket_id,
        outcome_notes=req.outcome_notes,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found.",
        )
    return SuccessResponse(message=f"Ticket {ticket_id[:8]} closed.")


@router.get(
    "/lawyers",
    summary="Admin fetches list of all lawyers (for assignment dropdowns)",
    response_model=List[LawyerSummaryResponse],
)
async def admin_list_lawyers(
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
):
    try:
        return user_service.get_all_lawyers_with_cal()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.patch(
    "/lawyers/{lawyer_id}/cal-credentials",
    summary="Admin sets a lawyer's Cal.com credentials",
    response_model=SuccessResponse,
)
async def admin_set_lawyer_cal_credentials(
    lawyer_id: str,
    cal_api_key: str,
    cal_event_type_id: str,
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
):
    try:
        success = user_service.update_lawyer_cal_credentials(
            lawyer_id=lawyer_id,
            cal_api_key=cal_api_key,
            cal_event_type_id=cal_event_type_id,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lawyer profile not found. Ensure the user has been promoted to lawyer.",
            )
        return SuccessResponse(message="Cal.com credentials saved.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get(
    "/domain-analytics",
    summary="Get user query domain distribution analytics",
    response_model=DomainAnalyticsResponse,
)
async def get_domain_analytics(
    current_user: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
):
    try:
        return user_service.get_domain_analytics()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get(
    "/sla-report",
    summary="Get SLA alerts, average response times, and lawyer performance",
    response_model=SLAReportResponse,
)
async def get_sla_report(
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    hitl_service: HitlService = Depends(get_hitl_service),
    user_service: UserService = Depends(get_user_service),
):
    try:
        svc = _hitl_service or hitl_service
        if user_service and hasattr(user_service, "_supabase"):
            svc._user_svc_supabase = user_service._supabase
            svc._supabase = user_service._supabase
        return svc.get_sla_report()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))






@router.patch(
    "/lawyers/{lawyer_id}/specialization",
    summary="Admin overrides a lawyer's specialization settings",
    response_model=Dict[str, Any],
)
async def admin_set_lawyer_specialization(
    lawyer_id: str,
    req: AdminSpecializationRequest,
    background_tasks: BackgroundTasks,
    current_admin: ClerkUser = Depends(require_db_role("admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
    email_service: Optional[EmailService] = Depends(get_email_service),
):
    try:
        updated_profile = user_service.update_lawyer_specialization(
            lawyer_id=lawyer_id,
            expertise_domains=req.expertise_domains,
            specialization_label=req.specialization_label,
        )
        if not updated_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lawyer profile not found. Ensure the user has been promoted to lawyer.",
            )

        if email_service:
            try:
                lawyer_info = user_service.get_lawyer_email_and_name(lawyer_id)
                if lawyer_info and lawyer_info.get("email"):
                    background_tasks.add_task(
                        email_service.send_specialization_override_to_lawyer,
                        to_email=lawyer_info["email"],
                        lawyer_name=lawyer_info["name"],
                        specialization_label=req.specialization_label,
                        expertise_domains=req.expertise_domains,
                    )
            except Exception as mail_err:
                logger.warning(f"⚠️ Failed to queue lawyer specialization override email: {mail_err}")

        return {"status": "success", "message": "Lawyer specialization updated by admin.", "profile": updated_profile}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))