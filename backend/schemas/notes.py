from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class NoteCreate(BaseModel):
    title: str = Field(..., description="The title of the note.")
    content: str = Field(..., description="The textual content of the note.")

class NoteUpdate(BaseModel):
    title: str = Field(..., description="The title of the note.")
    content: str = Field(..., description="The textual content of the note.")

class NoteResponse(BaseModel):
    id: str
    lawyer_id: str
    title: str
    content: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
