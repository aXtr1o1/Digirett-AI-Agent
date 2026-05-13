import logging
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from schemas.requests import ConversationCreate
from schemas.responses import (
    ConversationHistoryResponse,
    ConversationResponse,
    MessageResponse,
)
from core.auth import ClerkUser, get_current_user

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

router = APIRouter()

# UUID v4 pattern
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_conversation_service = None
_message_service = None
_user_service = None
_hitl_service = None


def _is_valid_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value.strip())) if value else False


def set_services(conversation_service, message_service, user_service, hitl_service) -> None:
    global _conversation_service, _message_service, _user_service, _hitl_service
    _conversation_service = conversation_service
    _message_service = message_service
    _user_service = user_service
    _hitl_service = hitl_service




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
    user: ClerkUser = Depends(get_current_user),
):
    
    try:
        raw_json = await request.json()
    except Exception:
        raw_json = {}

    # Optional: we can ignore body.user_id and just use the authenticated user
    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    try:
        conversation = _conversation_service.create_conversation(
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
    user: ClerkUser = Depends(get_current_user),
):
    """Return all non-deleted conversations for the current authenticated user, newest first."""

    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    try:
        conversations = _conversation_service.get_user_conversations(
            user_id=internal_user_id,
            limit=limit,
            offset=offset,
        )
        
        # Inject is_escalated status efficiently
        conv_ids = [c["conversation_id"] for c in conversations]
        escalated_ids = _hitl_service.get_escalated_conversation_ids(conv_ids)
        for c in conversations:
            c["is_escalated"] = c["conversation_id"] in escalated_ids

        # API-4: user exists but zero conversations → 200 []
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
    conversation_id: str,
    user: ClerkUser = Depends(get_current_user),
):

    # API-2: not a valid UUID → 400
    if not _is_valid_uuid(conversation_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation_id format. Must be a valid UUID.",
        )

    try:
        conversation = _conversation_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            )

        internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
        
        # Check authorization: Owner, Admin, or Assigned Lawyer
        is_owner = conversation.get("user_id") == internal_user_id
        is_admin = user.role == "admin"
        is_assigned_lawyer = False
        
        if not is_owner and not is_admin and user.role == "lawyer":
            # Check if this lawyer is assigned to a ticket for this conversation
            ticket = _hitl_service.get_ticket_by_conversation(conversation_id)
            if ticket and ticket.get("assigned_lawyer_id") == internal_user_id:
                is_assigned_lawyer = True

        if not (is_owner or is_admin or is_assigned_lawyer):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this conversation.",
            )

        conversation["is_escalated"] = _hitl_service.is_conversation_escalated(conversation_id)

        messages = _message_service.get_conversation_messages(conversation_id)

        return ConversationHistoryResponse(
            conversation=ConversationResponse(**conversation),
            messages=[MessageResponse(**m) for m in messages],
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_conversation failed | id={conversation_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch conversation: {exc}",
        )




@router.delete(
    "/conversations/{conversation_id}",
    tags=["Conversations"],
    summary="Delete a conversation (soft delete)",
)
@limiter.limit("100/minute")
async def delete_conversation(
    request: Request,
    conversation_id: str,
    user: ClerkUser = Depends(get_current_user),
):
    """Soft-delete a conversation and all its messages."""

    # API-2 & API-4: not a valid UUID → 400
    if not _is_valid_uuid(conversation_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation_id format. Must be a valid UUID.",
        )

    try:
        # API-3: check existence before deleting — Supabase soft_delete
        # returns True even when 0 rows matched (UPDATE with no match = success).
        existing = _conversation_service.get_conversation(conversation_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or already deleted.",
            )

        internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
        if existing.get("user_id") != internal_user_id and user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this conversation.",
            )

        _conversation_service.delete_conversation(conversation_id)
        return {"message": "Conversation deleted", "conversation_id": conversation_id}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"delete_conversation failed | id={conversation_id} | {exc}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete conversation: {exc}",
        )