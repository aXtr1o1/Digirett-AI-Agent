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


# ── Cal.com Response Schemas ───────────────────────────────────────────
class CalSlotsResponse(BaseModel):
    ticket_id: str
    lawyer_id: Optional[str] = None
    slots: Dict[str, Any]


class CalBookingResponse(BaseModel):
    ticket_id: str
    cal_booking_id: Optional[Any] = None
    uid: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    status: Optional[str] = None
    message: str


class CalLawyerConfigResponse(BaseModel):
    cal_event_type_id: str
    cal_api_key: str


class CalMessageResponse(BaseModel):
    message: str


class CalWebhookResponse(BaseModel):
    status: str
    ticket_id: Optional[str] = None
    cal_booking_id: Optional[str] = None
    booking_url: Optional[str] = None
    action: Optional[str] = None
    reason: Optional[str] = None


class AcceptInviteResponse(BaseModel):
    status: str = "success"
    message: str
    role: Optional[str] = None


# ── Document Agent Response Schemas ────────────────────────────────────
class DocumentUploadResponse(BaseModel):
    document_id: str
    file_name: str
    file_type: str
    char_count: int
    upload_order: int
    docs_remaining: int
    message: str
    duplicate: bool = False


class SessionStatusResponse(BaseModel):
    conversation_id: str
    doc_count: int
    turn_count: int
    token_count: int = 0
    docs_remaining: int
    turns_remaining: int
    tokens_remaining: int = 0
    has_documents: bool
    session_active: bool
    reset_at: Optional[str] = None
    docs: List[Any] = Field(default_factory=list)


# ── Billing Response Schemas ───────────────────────────────────────────
class BillingPortalResponse(BaseModel):
    status: str = "success"
    url: str


# ── Admin Response Schemas ─────────────────────────────────────────────
class SuccessResponse(BaseModel):
    status: str = "success"
    message: str


class LawyerSummaryResponse(BaseModel):
    user_id: str
    email: Optional[str] = None
    display_name: str
    cal_configured: bool
    expertise_domains: List[str] = Field(default_factory=list)
    specialization_label: Optional[str] = None


class AverageResponseTimes(BaseModel):
    avg_claim_hours: float
    avg_book_hours: float
    avg_resolve_days: float


class LawyerPerformanceMetric(BaseModel):
    lawyer_id: str
    name: str
    tickets: int
    avg_resolve_days: Optional[float] = None
    rating: Optional[float] = None


class SLAReportResponse(BaseModel):
    active_breaches: List[Dict[str, Any]] = Field(default_factory=list)
    average_response_times: AverageResponseTimes
    lawyer_performance: List[LawyerPerformanceMetric] = Field(default_factory=list)


class DomainAnalyticsItem(BaseModel):
    name: str
    raw_key: str
    is_canonical: bool
    queries: int
    percentage: float


class DomainAnalyticsResponse(BaseModel):
    total: int
    distribution: List[DomainAnalyticsItem] = Field(default_factory=list)