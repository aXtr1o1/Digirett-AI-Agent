from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class NoteBase(BaseModel):
    title: str = Field(..., description="The title of the note.")
    content: str = Field(..., description="The textual content of the note.")


class NoteCreate(NoteBase):
    pass


class NoteUpdate(NoteBase):
    pass


class NoteResponse(NoteBase):
    id: UUID
    lawyer_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
