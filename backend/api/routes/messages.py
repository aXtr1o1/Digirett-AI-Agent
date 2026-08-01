"""
api/routes/messages.py — Conversation message endpoints.

Refactored according to TL code review guidelines:
- Pure FastAPI Dependency Injection via Request.app.state
- Requires Depends(get_current_user) authentication & ownership authorization
- Native UUID path parameter validation (conversation_id: UUID)
- Single query optimization (get_conversation_messages_or_404)
- Standardized error logging without raw internal leakage
"""

import logging
from typing import List, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.auth import ClerkUser, get_current_user
from schemas.responses import MessageResponse
from services.conversation_service import ConversationService
from services.message_service import MessageService
from services.user_service import UserService

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


# ── Dependency Resolvers ─────────────────────────────────────────────

def get_message_service(request: Request) -> MessageService:
    svc = getattr(request.app.state, "message_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MessageService is not initialized on application state.",
        )
    return svc


def get_conversation_service(request: Request) -> ConversationService:
    svc = getattr(request.app.state, "conversation_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ConversationService is not initialized on application state.",
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


def _authorize_conversation_access(
    conversation_id: str,
    user_context: Tuple[ClerkUser, str],
    conversation_service: ConversationService,
):
    user, internal_user_id = user_context
    conv = conversation_service.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    if conv.get("user_id") != internal_user_id and user.role not in ("admin", "system_admin", "lawyer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own this conversation.",
        )
    return conv


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ROUTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/messages/{conversation_id}",
    response_model=List[MessageResponse],
    tags=["Messages"],
    summary="Fetch all messages for a conversation",
)
@limiter.limit("100/minute")
async def get_messages(
    request: Request,
    conversation_id: UUID,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    message_service: MessageService = Depends(get_message_service),
    conversation_service: ConversationService = Depends(get_conversation_service),
):
    conv_id_str = str(conversation_id)

    # 1. Authenticate & Authorize Access
    _authorize_conversation_access(conv_id_str, user_context, conversation_service)

    # 2. Fetch Messages
    try:
        messages = message_service.get_conversation_messages(conv_id_str)
        return [MessageResponse(**m) for m in messages]
    except Exception as exc:
        logger.exception(f"❌ get_messages failed | conversation={conv_id_str} | {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch messages.",
        )