

import logging
from typing import List

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

# Injected from main.py via set_services()
_conversation_service = None
_message_service = None


def set_services(conversation_service, message_service) -> None:
    global _conversation_service, _message_service
    _conversation_service = conversation_service
    _message_service = message_service


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CREATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
        conversation = _conversation_service.create_conversation(
            user_id=body.user_id,
            title=body.title,
        )
        return ConversationResponse(**conversation)

    except Exception as exc:
        logger.error(f" create_conversation failed | user={body.user_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create conversation: {exc}",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# READ — SINGLE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationHistoryResponse,
    tags=["Conversations"],
    summary="Get conversation with all messages",
)
@limiter.limit("100/minute")
async def get_conversation(request: Request, conversation_id: str):
    try:
        conversation = _conversation_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        messages = _message_service.get_conversation_messages(conversation_id)

        return ConversationHistoryResponse(
            conversation=ConversationResponse(**conversation),
            messages=[MessageResponse(**m) for m in messages],
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f" get_conversation failed | id={conversation_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch conversation: {exc}",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# READ — USER LIST
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
    try:
        conversations = _conversation_service.get_user_conversations(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        return [ConversationResponse(**c) for c in conversations]

    except Exception as exc:
        logger.error(f" get_user_conversations failed | user={user_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch conversations: {exc}",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DELETE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.delete(
    "/conversations/{conversation_id}",
    tags=["Conversations"],
    summary="Delete a conversation (soft delete)",
)
@limiter.limit("100/minute")
async def delete_conversation(request: Request, conversation_id: str):
    """Soft-delete a conversation and all its messages."""
    try:
        success = _conversation_service.delete_conversation(conversation_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or already deleted",
            )
        return {"message": "Conversation deleted", "conversation_id": conversation_id}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f" delete_conversation failed | id={conversation_id} | {exc}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete conversation: {exc}",
        )