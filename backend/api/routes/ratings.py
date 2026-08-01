"""
api/routes/ratings.py — Consultation feedback and rating endpoints.

Refactored according to TL code review guidelines:
- Encapsulated DB & notification logic inside RatingService
- Pure FastAPI Dependency Injection via Request.app.state
- Reusable get_current_internal_user dependency
- Configurable settings.LOW_RATING_THRESHOLD
- Typed Pydantic Response Models (RatingSubmitResponse, LawyerRatingResponse, AdminRatingResponse)
"""

import logging
from typing import List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.auth import ClerkUser, get_current_user, require_db_role
from schemas.responses import AdminRatingResponse, LawyerRatingResponse, RatingSubmitResponse
from services.rating_service import RatingService
from services.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ratings", tags=["Ratings"])


# ── Dependency Resolvers ─────────────────────────────────────────────

def get_rating_service(request: Request) -> RatingService:
    svc = getattr(request.app.state, "rating_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RatingService is not initialized on application state.",
        )
    return svc


def get_user_service(request: Request) -> UserService:
    svc = getattr(request.app.state, "user_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UserService is not initialized on application state.",
        )
    return svc


def get_current_internal_user(
    user: ClerkUser = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> Tuple[ClerkUser, str]:
    internal_user_id = user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )
    return user, internal_user_id


class RatingSubmitRequest(BaseModel):
    ticket_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ROUTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "",
    response_model=RatingSubmitResponse,
    summary="Submit consultation feedback and rating",
)
async def submit_rating(
    req: RatingSubmitRequest,
    background_tasks: BackgroundTasks,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    rating_service: RatingService = Depends(get_rating_service),
):
    _, internal_user_id = user_context
    try:
        res = rating_service.submit_rating(
            internal_user_id=internal_user_id,
            ticket_id=req.ticket_id,
            rating=req.rating,
            comment=req.comment,
        )

        background_tasks.add_task(
            rating_service.send_rating_notification_task,
            ticket_id=req.ticket_id,
            lawyer_id=res["lawyer_id"],
            rating=req.rating,
            comment=req.comment,
        )

        return RatingSubmitResponse(status="success", message="Feedback submitted successfully.")
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.exception(f"❌ Failed to submit rating: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store feedback.",
        )


@router.get(
    "/lawyer",
    response_model=List[LawyerRatingResponse],
    summary="Get rating logs for the logged-in lawyer",
)
async def get_lawyer_ratings(
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    rating_service: RatingService = Depends(get_rating_service),
):
    user, internal_user_id = user_context
    user_role = getattr(user, "db_role", None) or user.role
    if user_role not in ("lawyer", "admin", "system_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only lawyers can view ratings.",
        )


    try:
        ratings = rating_service.get_lawyer_ratings(internal_user_id)
        return [LawyerRatingResponse(**r) for r in ratings]
    except Exception as exc:
        logger.exception(f"❌ Failed to fetch lawyer ratings: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch lawyer ratings.",
        )


@router.get(
    "/admin",
    response_model=List[AdminRatingResponse],
    summary="Get all ratings in the system for admin audit",
)
async def get_admin_ratings(
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    rating_service: RatingService = Depends(get_rating_service),
):
    user, _ = user_context
    user_role = getattr(user, "db_role", None) or user.role
    if user_role not in ("admin", "system_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin privileges required.",
        )

    try:
        ratings = rating_service.get_admin_ratings()
        return [AdminRatingResponse(**r) for r in ratings]
    except Exception as exc:
        logger.exception(f"❌ Failed to fetch admin ratings: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch admin ratings.",
        )
