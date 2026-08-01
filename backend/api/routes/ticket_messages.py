import logging
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel

from core.auth import ClerkUser, get_current_user
from schemas.responses import TicketMessageListResponse, TicketMessageReadResponse, TicketMessageResponse
from services.ticket_message_service import TicketMessageService
from services.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/hitl/tickets", tags=["HITL Messaging"])

def get_ticket_message_service(request: Request) -> TicketMessageService:
    svc = getattr(request.app.state, "ticket_message_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TicketMessageService is not initialized on application state.",
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


class MessageCreateRequest(BaseModel):
    content: str
    file_name: Optional[str] = None
    document_id: Optional[str] = None

@router.get(
    "/{ticket_id}/messages",
    response_model=TicketMessageListResponse,
    summary="Fetch message thread for a consultation ticket",
)
async def get_ticket_messages(
    ticket_id: UUID,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    ticket_message_service: TicketMessageService = Depends(get_ticket_message_service),
    user_service: UserService = Depends(get_user_service),
):
    user, internal_user_id = user_context
    user_role = getattr(user, "db_role", None) or user_service.get_user_role(user.clerk_user_id) or user.role
    ticket_id_str = str(ticket_id)

    try:
        messages = ticket_message_service.get_messages(
            ticket_id=ticket_id_str,
            internal_user_id=internal_user_id,
            user_role=user_role,
        )
        return TicketMessageListResponse(messages=[TicketMessageResponse(**m) for m in messages])
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        logger.exception(f" Failed to fetch ticket messages: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ticket messages.",
        )


@router.post(
    "/{ticket_id}/messages",
    response_model=TicketMessageResponse,
    summary="Send a message on a consultation ticket thread",
)
async def create_ticket_message(
    ticket_id: UUID,
    req: MessageCreateRequest,
    background_tasks: BackgroundTasks,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    ticket_message_service: TicketMessageService = Depends(get_ticket_message_service),
    user_service: UserService = Depends(get_user_service),
):
    user, internal_user_id = user_context
    user_role = getattr(user, "db_role", None) or user_service.get_user_role(user.clerk_user_id) or user.role
    ticket_id_str = str(ticket_id)

    try:
        created = ticket_message_service.create_message(
            ticket_id=ticket_id_str,
            sender_id=internal_user_id,
            sender_role=user_role,
            content=req.content,
            file_name=req.file_name,
            document_id=req.document_id,
        )

        background_tasks.add_task(
            ticket_message_service.send_message_notification_task,
            ticket_id=ticket_id_str,
            sender_id=internal_user_id,
            sender_role=user_role,
            message_content=req.content,
        )

        return TicketMessageResponse(**created)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        logger.exception(f" Failed to create ticket message: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message.",
        )


@router.patch(
    "/{ticket_id}/messages/read",
    response_model=TicketMessageReadResponse,
    summary="Mark unread messages sent by opposite party as read",
)
async def mark_messages_read(
    ticket_id: UUID,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    ticket_message_service: TicketMessageService = Depends(get_ticket_message_service),
    user_service: UserService = Depends(get_user_service),
):
    user, internal_user_id = user_context
    user_role = getattr(user, "db_role", None) or user_service.get_user_role(user.clerk_user_id) or user.role
    ticket_id_str = str(ticket_id)

    try:
        marked_count = ticket_message_service.mark_messages_read(
            ticket_id=ticket_id_str,
            internal_user_id=internal_user_id,
            user_role=user_role,
        )
        return TicketMessageReadResponse(status="success", marked_count=marked_count)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        logger.exception(f" Failed to mark messages as read: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark messages as read.",
        )

