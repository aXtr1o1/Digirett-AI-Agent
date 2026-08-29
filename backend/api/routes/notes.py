import logging
from typing import List, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from core.auth import ClerkUser, require_db_role
from schemas.notes import NoteCreate, NoteResponse, NoteUpdate
from schemas.responses import NoteDeleteResponse
from services.notes_service import NotesService
from services.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notes", tags=["Lawyer Notes"])

def get_notes_service(request: Request) -> NotesService:
    svc = getattr(request.app.state, "notes_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NotesService is not initialized on application state.",
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
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin", "system_admin")),
    user_service: UserService = Depends(get_user_service),
) -> Tuple[ClerkUser, str]:
    internal_user_id = user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id, email=current_lawyer.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )
    return current_lawyer, internal_user_id

@router.get("/", response_model=List[NoteResponse], summary="Get all notes for current lawyer")
async def get_notes(
    lawyer_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    notes_service: NotesService = Depends(get_notes_service),
):
    """Fetch all personal notes for the authenticated lawyer."""
    _, lawyer_id = lawyer_context
    try:
        return notes_service.get_notes_by_lawyer(lawyer_id)
    except Exception as exc:
        logger.exception(f" Failed to fetch notes for lawyer {lawyer_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch notes.",
        )


@router.post("/", response_model=NoteResponse, summary="Create a new note")
async def create_note(
    req: NoteCreate,
    lawyer_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    notes_service: NotesService = Depends(get_notes_service),
):
    """Create a new personal note."""
    _, lawyer_id = lawyer_context
    note = notes_service.create_note(lawyer_id, req.title, req.content)
    if not note:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create note.")
    return note


@router.put("/{note_id}", response_model=NoteResponse, summary="Update an existing note")
async def update_note(
    note_id: UUID,
    req: NoteUpdate,
    lawyer_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    notes_service: NotesService = Depends(get_notes_service),
):
    """Update a personal note."""
    _, lawyer_id = lawyer_context
    note_id_str = str(note_id)
    note = notes_service.update_note(note_id_str, lawyer_id, req.title, req.content)
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found or you don't have permission to update it.",
        )
    return note


@router.delete("/{note_id}", response_model=NoteDeleteResponse, summary="Delete a note")
async def delete_note(
    note_id: UUID,
    lawyer_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    notes_service: NotesService = Depends(get_notes_service),
):
    """Delete a personal note."""
    _, lawyer_id = lawyer_context
    note_id_str = str(note_id)
    success = notes_service.delete_note(note_id_str, lawyer_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found or could not be deleted.",
        )
    return NoteDeleteResponse(
        success=True,
        message="Note deleted successfully.",
        note_id=note_id_str,
    )