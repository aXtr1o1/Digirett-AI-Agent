import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.auth import ClerkUser, get_current_user
from schemas.requests import LibrarySaveRequest, LibraryNoteUpdateRequest
from schemas.responses import LibraryItemResponse

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

_library_service = None
_user_service = None

def set_services(library_service, user_service) -> None:
    global _library_service, _user_service
    _library_service = library_service
    _user_service = user_service

@router.post(
    "/library/save",
    response_model=LibraryItemResponse,
    tags=["Library"],
    summary="Save a message to the library",
)
@limiter.limit("60/minute")
async def save_to_library(
    request: Request,
    body: LibrarySaveRequest,
    user: ClerkUser = Depends(get_current_user),
):
    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    try:
        saved = _library_service.save_message(
            user_id=internal_user_id,
            message_id=body.message_id,
            note=body.note
        )
        if not saved:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save message to library."
            )
        
        # Load the saved message to return in full LibraryItemResponse format
        messages = _library_service.get_saved_messages(internal_user_id)
        for msg in messages:
            if msg["message_id"] == body.message_id:
                return LibraryItemResponse(**msg)
                
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Saved message could not be fetched."
        )
    except Exception as exc:
        logger.error(f"Error saving to library: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )

@router.get(
    "/library",
    response_model=List[LibraryItemResponse],
    tags=["Library"],
    summary="Get all saved messages in user library",
)
@limiter.limit("60/minute")
async def get_library(
    request: Request,
    user: ClerkUser = Depends(get_current_user),
):
    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    try:
        messages = _library_service.get_saved_messages(internal_user_id)
        return [LibraryItemResponse(**m) for m in messages]
    except Exception as exc:
        logger.error(f"Error getting library: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )

@router.delete(
    "/library/{message_id}",
    tags=["Library"],
    summary="Remove a message from the library",
)
@limiter.limit("60/minute")
async def unsave_from_library(
    request: Request,
    message_id: str,
    user: ClerkUser = Depends(get_current_user),
):
    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    try:
        success = _library_service.delete_saved_message(message_id, internal_user_id)
        return {"success": success}
    except Exception as exc:
        logger.error(f"Error deleting from library: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )

@router.patch(
    "/library/{message_id}",
    response_model=LibraryItemResponse,
    tags=["Library"],
    summary="Update notes/annotations for a saved message",
)
@limiter.limit("60/minute")
async def update_library_note(
    request: Request,
    message_id: str,
    body: LibraryNoteUpdateRequest,
    user: ClerkUser = Depends(get_current_user),
):
    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    try:
        _library_service.update_saved_message_note(message_id, internal_user_id, body.note)
        
        # Return updated item
        messages = _library_service.get_saved_messages(internal_user_id)
        for msg in messages:
            if msg["message_id"] == message_id:
                return LibraryItemResponse(**msg)
                
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved message not found."
        )
    except Exception as exc:
        logger.error(f"Error updating note: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )
