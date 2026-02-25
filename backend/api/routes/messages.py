import logging
import re
from typing import List

from fastapi import APIRouter, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from schemas.responses import MessageResponse

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_message_service = None
_conversation_service = None


def _is_valid_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value.strip())) if value else False


def set_services(message_service, conversation_service=None) -> None:
    global _message_service, _conversation_service
    _message_service = message_service
    _conversation_service = conversation_service




@router.get(
    "/messages/{conversation_id}",
    response_model=List[MessageResponse],
    tags=["Messages"],
    summary="Fetch all messages for a conversation",
)
@limiter.limit("100/minute")
async def get_messages(request: Request, conversation_id: str):

    # API-2: not a valid UUID → 400
    if not _is_valid_uuid(conversation_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation_id format. Must be a valid UUID.",
        )

    try:
        # API-3: get_conversation_messages returns [] for both
        # "exists but empty" and "does not exist" — check existence first.
        if _conversation_service:
            conversation = _conversation_service.get_conversation(conversation_id)
            if not conversation:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found.",
                )

        messages = _message_service.get_conversation_messages(conversation_id)
        return [MessageResponse(**m) for m in messages]

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"get_messages failed | conversation={conversation_id} | {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch messages.",
        )