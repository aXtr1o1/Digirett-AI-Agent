import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status

from core.auth import ClerkUser, require_db_role
from services.notes_service import NotesService
from services.user_service import UserService
from schemas.notes import NoteCreate, NoteUpdate, NoteResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notes", tags=["Lawyer Notes"])

_notes_service: Optional[NotesService] = None
_user_service: Optional[UserService] = None

def set_services(notes_svc: NotesService, user_svc: UserService) -> None:
    global _notes_service, _user_service
    _notes_service = notes_svc
    _user_service = user_svc

@router.get("/", response_model=List[NoteResponse], summary="Get all notes for current lawyer")
async def get_notes(
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin"))
):
    """Fetch all personal notes for the authenticated lawyer."""
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    notes = _notes_service.get_notes_by_lawyer(lawyer_id)
    return notes

@router.post("/", response_model=NoteResponse, summary="Create a new note")
async def create_note(
    req: NoteCreate,
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin"))
):
    """Create a new personal note."""
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    note = _notes_service.create_note(lawyer_id, req.title, req.content)
    if not note:
        raise HTTPException(status_code=500, detail="Failed to create note.")
    return note

@router.put("/{note_id}", response_model=NoteResponse, summary="Update an existing note")
async def update_note(
    note_id: str,
    req: NoteUpdate,
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin"))
):
    """Update a personal note."""
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    note = _notes_service.update_note(note_id, lawyer_id, req.title, req.content)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found or you don't have permission to update it.")
    return note

@router.delete("/{note_id}", summary="Delete a note")
async def delete_note(
    note_id: str,
    current_lawyer: ClerkUser = Depends(require_db_role("lawyer", "admin"))
):
    """Delete a personal note."""
    lawyer_id = _user_service.get_user_id_from_clerk_id(current_lawyer.clerk_user_id)
    success = _notes_service.delete_note(note_id, lawyer_id)
    if not success:
        raise HTTPException(status_code=404, detail="Note not found or could not be deleted.")
    return {"message": "Note deleted successfully."}