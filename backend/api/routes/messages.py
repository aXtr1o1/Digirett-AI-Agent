
import logging
from typing import List

from fastapi import APIRouter, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from schemas.responses import MessageResponse

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# Injected from main.py via set_services()
_message_service = None


def set_services(message_service) -> None:
    global _message_service
    _message_service = message_service


@router.get(
    "/messages/{conversation_id}",
    response_model=List[MessageResponse],
    tags=["Messages"],
    summary="Fetch all messages for a conversation",
)
@limiter.limit("100/minute")
async def get_messages(request: Request, conversation_id: str):

    try:
        messages = _message_service.get_conversation_messages(conversation_id)
        return [MessageResponse(**m) for m in messages]

    except Exception as exc:
        logger.error(
            f" get_messages failed | conversation={conversation_id} | {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch messages",
        )