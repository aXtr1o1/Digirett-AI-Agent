import logging
from typing import List, Optional, Tuple

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.auth import ClerkUser, get_current_user
from schemas.requests import ConversationCreate
from schemas.responses import (
    ConversationHistoryResponse,
    ConversationResponse,
    DeleteConversationResponse,
    MessageResponse,
)
from services.conversation_service import ConversationService
from services.document_service import DocumentService
from services.hitl_service import HitlService
from services.message_service import MessageService
from services.user_service import UserService

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

def get_conversation_service(request: Request) -> ConversationService:
    svc = getattr(request.app.state, "conversation_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ConversationService is not initialized on application state.",
        )
    return svc


def get_message_service(request: Request) -> MessageService:
    svc = getattr(request.app.state, "message_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MessageService is not initialized on application state.",
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


def get_hitl_service(request: Request) -> HitlService:
    svc = getattr(request.app.state, "hitl_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HitlService is not initialized on application state.",
        )
    return svc


def get_document_service(request: Request) -> Optional[DocumentService]:
    return getattr(request.app.state, "document_service", None)


def get_current_internal_user(
    user: ClerkUser = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> Tuple[ClerkUser, str]:
    """Resolves current authenticated user and internal database user_id."""
    internal_user_id = user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )
    return user, internal_user_id

def _authorize_conversation_access(
    conversation: dict,
    internal_user_id: str,
    user_role: str,
    allowed_roles: Optional[List[str]] = None,
) -> None:
    """Verifies that the internal user owns the conversation or has authorized role."""
    allowed = allowed_roles or ["admin", "lawyer", "system_admin"]
    is_owner = conversation.get("user_id") == internal_user_id

    if not is_owner and user_role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this conversation.",
        )

@router.post(
    "/conversations",
    response_model=ConversationResponse,
    tags=["Conversations"],
    summary="Create a new conversation",
)
@limiter.limit("100/minute")
async def create_conversation(
    request: Request,
    body: ConversationCreate,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    conversation_service: ConversationService = Depends(get_conversation_service),
    document_service: Optional[DocumentService] = Depends(get_document_service),
):
    user, internal_user_id = user_context

    try:
        if document_service:
            role = getattr(user, "role", "user")
            allowed_turn, _ = document_service.check_turn_limit(internal_user_id, user_role=role)
            if not allowed_turn:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Message limit reached. Your session resets every 4 hours.",
                )

            allowed_token, _ = document_service.check_token_limit(internal_user_id, user_role=role)
            if not allowed_token:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Token limit reached. Your session resets every 4 hours.",
                )

        conversation = conversation_service.create_conversation(
            user_id=internal_user_id,
            title=body.title,
        )
        return ConversationResponse(**conversation)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"create_conversation failed | user={internal_user_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create conversation: {exc}",
        )


@router.get(
    "/conversations/me",
    response_model=List[ConversationResponse],
    tags=["Conversations"],
    summary="List all conversations for the current user",
)
@limiter.limit("100/minute")
async def get_my_conversations(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    conversation_service: ConversationService = Depends(get_conversation_service),
    hitl_service: HitlService = Depends(get_hitl_service),
):
    """Return all non-deleted conversations for the current authenticated user, newest first."""
    _, internal_user_id = user_context

    try:
        conversations = conversation_service.get_user_conversations(
            user_id=internal_user_id,
            limit=limit,
            offset=offset,
        )

        conv_ids = [c["conversation_id"] for c in conversations]
        escalated_ids = hitl_service.get_escalated_conversation_ids(conv_ids)
        for c in conversations:
            c["is_escalated"] = c["conversation_id"] in escalated_ids

        return [ConversationResponse(**c) for c in conversations]

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_user_conversations failed | user={internal_user_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch conversations: {exc}",
        )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationHistoryResponse,
    tags=["Conversations"],
    summary="Get conversation with all messages",
)
@limiter.limit("100/minute")
async def get_conversation(
    request: Request,
    conversation_id: UUID,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    conversation_service: ConversationService = Depends(get_conversation_service),
    message_service: MessageService = Depends(get_message_service),
    hitl_service: HitlService = Depends(get_hitl_service),
    user_service: UserService = Depends(get_user_service),
):
    """Fetches a conversation history by UUID."""
    user, internal_user_id = user_context
    conv_id_str = str(conversation_id)

    try:
        conversation = conversation_service.get_conversation(conv_id_str)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            )

        # Resolve authoritative role using UserService (zero direct Supabase calls)
        db_role = user_service.get_user_role(user.clerk_user_id) or user.role
        _authorize_conversation_access(conversation, internal_user_id, db_role)

        conversation["is_escalated"] = hitl_service.is_conversation_escalated(conv_id_str)
        messages = message_service.get_conversation_messages(conv_id_str)

        return ConversationHistoryResponse(
            conversation=ConversationResponse(**conversation),
            messages=[MessageResponse(**m) for m in messages],
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_conversation failed | id={conv_id_str} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch conversation: {exc}",
        )


@router.delete(
    "/conversations/{conversation_id}",
    response_model=DeleteConversationResponse,
    tags=["Conversations"],
    summary="Delete a conversation (soft delete)",
)
@limiter.limit("100/minute")
async def delete_conversation(
    request: Request,
    conversation_id: UUID,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    conversation_service: ConversationService = Depends(get_conversation_service),
):
    """Soft-delete a conversation and all its messages."""
    user, internal_user_id = user_context
    conv_id_str = str(conversation_id)

    try:
        existing = conversation_service.get_conversation(conv_id_str)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or already deleted.",
            )

        _authorize_conversation_access(existing, internal_user_id, user.role, allowed_roles=["admin"])
        conversation_service.delete_conversation(conv_id_str)

        return DeleteConversationResponse(
            message="Conversation deleted",
            conversation_id=conv_id_str,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"delete_conversation failed | id={conv_id_str} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete conversation: {exc}",
        )