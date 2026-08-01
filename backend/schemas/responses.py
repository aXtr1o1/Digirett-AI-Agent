from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class TimestampedModel(BaseModel):
    created_at: datetime
    updated_at: Optional[datetime] = None


class BaseEntityResponse(TimestampedModel):
    id: Union[UUID, str]


# ── Chat ─────────────────────────────────────────────────────────────────────

class GoldenAnswerShort(BaseModel):
    conclusion: str
    citations: List[str] = Field(default_factory=list)


class SourceMetadata(BaseModel):
    domain: Optional[str] = None
    subdomain: Optional[str] = None
    section_ref: Optional[str] = None
    jurisdiction: Optional[str] = None


class Source(BaseModel):
    """A single retrieved source document."""
    title: str
    url: str
    chunk_text: Optional[str] = None
    relevance_score: Optional[float] = None
    metadata: SourceMetadata = Field(default_factory=SourceMetadata)


class ChatResponse(BaseModel):
    """Non-streaming chat response (used internally and for docs)."""
    answer: str
    golden_answer_short: Optional[GoldenAnswerShort] = None
    sources: List[Source] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    conversation_id: Optional[Union[UUID, str]] = None
    message_id: Optional[Union[UUID, str]] = None


# ── Conversations ─────────────────────────────────────────────────────────────

class ConversationResponse(TimestampedModel):
    """Returned whenever a conversation is created or fetched."""
    conversation_id: Union[UUID, str]
    user_id: Union[UUID, str]
    title: Optional[str] = None
    message_count: int = 0
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False
    is_escalated: bool = False


class MessageResponse(BaseModel):
    """A single message within a conversation."""
    message_id: Union[UUID, str]
    conversation_id: Union[UUID, str]
    role: MessageRole
    content: str
    created_at: datetime
    metadata: Optional[Dict[str, Any]] = None
    sources: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    type: str = "text"
    file_name: Optional[str] = None


class ConversationHistoryResponse(BaseModel):
    """Full conversation with all messages."""
    conversation: ConversationResponse
    messages: List[MessageResponse]
    summary: Optional[str] = None


class DeleteConversationResponse(BaseModel):
    """Response returned upon soft-deleting a conversation."""
    message: str
    conversation_id: Union[UUID, str]


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """System health check response."""
    status: HealthStatus
    version: str
    milvus_connected: bool
    llm_connected: bool
    cache_connected: bool
    supabase_connected: bool
    total_queries: int = 0
    uptime: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Search ────────────────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    """A single Milvus search result."""
    id: Union[UUID, str]
    title: str
    content: str
    url: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Response from the raw vector search endpoint."""
    results: List[SearchResult] = Field(default_factory=list)
    total_found: int
    query_time: float


class LibraryDocumentResponse(BaseModel):
    """A document saved in user's library."""
    id: Union[UUID, str]
    user_id: Union[UUID, str]
    file_name: str
    file_type: str
    char_count: int
    note: str = ""
    created_at: datetime
    expires_at: datetime


class InviteVerificationResponse(BaseModel):
    """Response returned when verifying an invitation token."""
    valid: bool
    reason: Optional[str] = None
    role: Optional[str] = None
    masked_email: Optional[str] = None
    message: str


class LibraryDeleteResponse(BaseModel):
    """Response returned when deleting a document from the library."""
    success: bool
    message: str
    document_id: Union[UUID, str]


class NoteDeleteResponse(BaseModel):
    """Response returned when deleting a lawyer note."""
    success: bool
    message: str
    note_id: Union[UUID, str]


class RatingSubmitResponse(BaseModel):
    """Response returned when submitting consultation rating."""
    status: str
    message: str


class LawyerRatingResponse(BaseModel):
    """Rating row for lawyer dashboard."""
    rating_id: Union[UUID, str]
    ticket_id: Union[UUID, str]
    rating: int
    comment: Optional[str] = None
    created_at: str


class AdminRatingResponse(BaseModel):
    """Rating row for admin audit log."""
    rating_id: Union[UUID, str]
    ticket_id: Union[UUID, str]
    user_id: Union[UUID, str]
    lawyer_id: Union[UUID, str]
    rating: int
    comment: Optional[str] = None
    created_at: str
    lawyer_name: Optional[str] = None
    lawyer_email: Optional[str] = None


class TicketMessageResponse(BaseModel):
    """Single ticket message schema."""
    message_id: Union[UUID, str]
    ticket_id: Union[UUID, str]
    sender_id: Union[UUID, str]
    sender_role: str
    content: str
    file_name: Optional[str] = None
    document_id: Optional[Union[UUID, str]] = None
    created_at: str
    is_read: bool = False


class TicketMessageListResponse(BaseModel):
    """List of messages for a ticket thread."""
    messages: List[TicketMessageResponse] = Field(default_factory=list)


class TicketMessageReadResponse(BaseModel):
    """Response when marking messages as read."""
    status: str
    marked_count: int


class WebhookResponse(BaseModel):
    """Response model for webhook event handlers."""
    status: str
    message: Optional[str] = None
    reason: Optional[str] = None