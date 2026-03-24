import logging
import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from schemas.requests import ConversationCreate
from schemas.responses import (
    ConversationHistoryResponse,
    ConversationResponse,
    MessageResponse,
)

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# The one and only valid user in the system
DEFAULT_USER_ID = "2a06144d-4675-4c38-b7f8-13c02da91af5"

# UUID v4 pattern
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_conversation_service = None
_message_service = None


def _is_valid_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value.strip())) if value else False


def set_services(conversation_service, message_service) -> None:
    global _conversation_service, _message_service
    _conversation_service = conversation_service
    _message_service = message_service




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
):
    
    try:
        raw_json = await request.json()
    except Exception:
        raw_json = {}

    if "user_id" not in raw_json:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"loc": ["body", "user_id"], "msg": "field required", "type": "missing"}],
        )

    user_id = raw_json["user_id"]

    # API-3: user_id key present but value is empty string
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id must not be empty.",
        )

    # API-4: user_id is a real value but not the known user
    if user_id.strip() != DEFAULT_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {user_id}",
        )

    try:
        conversation = _conversation_service.create_conversation(
            user_id=user_id.strip(),
            title=body.title,
        )
        return ConversationResponse(**conversation)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"create_conversation failed | user={user_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create conversation: {exc}",
        )




@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationHistoryResponse,
    tags=["Conversations"],
    summary="Get conversation with all messages",
)
@limiter.limit("100/minute")
async def get_conversation(request: Request, conversation_id: str):

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




@router.get(
    "/conversations/user/{user_id}",
    response_model=List[ConversationResponse],
    tags=["Conversations"],
    summary="List all conversations for a user",
)
@limiter.limit("100/minute")
async def get_user_conversations(
    request: Request,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
):
    """Return all non-deleted conversations for a user, newest first."""

    # API-2: contains special chars like @, spaces → 400
    if not re.match(r"^[a-zA-Z0-9_\-]+$", user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format. Only alphanumeric characters, "
                   "hyphens, and underscores are allowed.",
        )

    # API-3: valid format but not a known user → 404
    if user_id != DEFAULT_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {user_id}",
        )

    try:
        conversations = _conversation_service.get_user_conversations(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        # API-4: user exists but zero conversations → 200 []
        return [ConversationResponse(**c) for c in conversations]

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_user_conversations failed | user={user_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch conversations: {exc}",
        )




@router.delete(
    "/conversations/{conversation_id}",
    tags=["Conversations"],
    summary="Delete a conversation (soft delete)",
)
@limiter.limit("100/minute")
async def delete_conversation(request: Request, conversation_id: str):
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