from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Body for POST /chat/stream"""

    query: str = Field(
        ...,
        min_length=1,
        max_length=20000,
        description="The user's question or message.",
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Existing conversation UUID. A new one is created when omitted.",
    )
    user_id: Optional[str] = Field(
        None,
        description="User UUID. Optional for MVP.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of Milvus chunks to retrieve (LEGAL queries only).",
    )
    include_sources: bool = Field(
        default=True,
        description="Whether to include source citations in the response.",
    )
    temperature: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="LLM temperature. Lower = more deterministic.",
    )
    skip_save_user: bool = Field(
        default=False,
        description="If True, skips saving the user message in save_exchange. Used when the message is already saved (e.g. file upload).",
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace.")
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "Hva er reglene for aksjeselskap i Norge?",
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "2a06144d-4675-4c38-b7f8-13c02da91af5",
                "top_k": 5,
                "include_sources": True,
                "temperature": 0.45,
            }
        }
    }


class ConversationCreate(BaseModel):
    """Body for POST /conversations"""

   
    user_id: Optional[str] = Field(
        None,
        description="UUID of the user creating the conversation.",
    )
    title: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional title. Auto-generated from first query when omitted.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": "2a06144d-4675-4c38-b7f8-13c02da91af5",
                "title": "Discussion about Company Law",
            }
        }
    }


class SearchRequest(BaseModel):
    """Body for POST /search (vector search without generation)."""

    query: str = Field(..., min_length=1, max_length=20000)
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.45, ge=0.0, le=1.0)


class LibraryNoteUpdateRequest(BaseModel):
    """Body for PATCH /library/{document_id}"""
    note: str = Field(..., description="Updated note/annotation content")