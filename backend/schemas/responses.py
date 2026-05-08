
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Chat ─────────────────────────────────────────────────────────────────────

class GoldenAnswerShort(BaseModel):
    conclusion: str
    citations: List[str] = Field(default_factory=list)


class Source(BaseModel):
    """A single retrieved source document."""
    title: str
    url: str
    chunk_text: Optional[str] = None
    relevance_score: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Non-streaming chat response (used internally and for docs)."""
    answer: str
    golden_answer_short: Optional[GoldenAnswerShort] = None
    sources: List[Source] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None


# ── Conversations ─────────────────────────────────────────────────────────────

class ConversationResponse(BaseModel):
    """Returned whenever a conversation is created or fetched."""
    conversation_id: str
    user_id: str
    title: Optional[str] = None
    message_count: int = 0
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False
    is_escalated: bool = False


class MessageResponse(BaseModel):
    """A single message within a conversation."""
    message_id: str
    conversation_id: str
    role: str   # "user" | "assistant"
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


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """System health check response."""
    status: str                    # "healthy" | "degraded"
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
    id: str
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