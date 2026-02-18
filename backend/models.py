"""
app/models.py
Pydantic models for request/response validation
UPDATED: Added conversation and message models
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID


# ============================================
# REQUEST MODELS - EXISTING (UPDATED)
# ============================================

class ChatRequest(BaseModel):
    """Chat request with RAG and conversation context"""
    query: str = Field(..., min_length=1, max_length=1000, description="User's question")
    conversation_id: Optional[str] = Field(None, description="Conversation ID (optional, auto-created if missing)")
    user_id: Optional[str] = Field(None, description="User ID (optional for MVP)")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of chunks to retrieve")
    include_sources: bool = Field(default=True, description="Include source citations")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="LLM temperature")

    @validator("query")
    def validate_query(cls, v):
        """Ensure query is not empty"""
        if not v.strip():
            raise ValueError("Query cannot be empty")
        return v.strip()

    class Config:
        schema_extra = {
            "example": {
                "query": "Hva er reglene for aksjeselskap i Norge?",
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "admin",
                "top_k": 3,
                "include_sources": True,
                "temperature": 0.7,
            }
        }


class SearchRequest(BaseModel):
    """Search request without generation"""
    query: str = Field(..., min_length=1, max_length=20000, description="Search query")
    top_k: int = Field(default=10, ge=1, le=50, description="Number of results")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum similarity score")

    class Config:
        schema_extra = {
            "example": {
                "query": "aksjelov generalforsamling",
                "top_k": 10,
                "min_score": 0.5,
            }
        }


class FeedbackRequest(BaseModel):
    """User feedback"""
    query_id: str = Field(..., description="Query identifier")
    rating: int = Field(..., ge=1, le=5, description="Rating 1-5")
    helpful: bool = Field(..., description="Was the answer helpful?")
    comment: Optional[str] = Field(None, max_length=500, description="Optional comment")

    class Config:
        schema_extra = {
            "example": {
                "query_id": "q_abc123",
                "rating": 4,
                "helpful": True,
                "comment": "Good answer but could be more detailed",
            }
        }

# ============================================
# CONVERSATION MODELS (NEW)
# ============================================

class ConversationCreate(BaseModel):
    """Create new conversation"""
    user_id: str = Field(default="2a06144d-4675-4c38-b7f8-13c02da91af5", description="User UUID")
    title: Optional[str] = Field(None, max_length=100, description="Conversation title")

    class Config:
        schema_extra = {
            "example": {
                "user_id": "2a06144d-4675-4c38-b7f8-13c02da91af5",
                "title": "Discussion about Company Law"
            }
        }


class ConversationResponse(BaseModel):
    """Conversation details"""
    conversation_id: str
    user_id: str  # ← Changed from int to str
    title: Optional[str]
    message_count: int = 0
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False

    class Config:
        schema_extra = {
            "example": {
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "2a06144d-4675-4c38-b7f8-13c02da91af5",
                "title": "Discussion about Company Law",
                "message_count": 15,
                "created_at": "2026-02-05T10:00:00Z",
                "updated_at": "2026-02-05T12:30:00Z",
                "is_deleted": False
            }
        }


class MessageResponse(BaseModel):
    """Single message in conversation"""
    message_id: str
    conversation_id: str
    role: str  # "user" or "assistant"
    content: str
    created_at: datetime
    metadata: Optional[Dict[str, Any]] = None
    sources: Optional[List[Dict[str, Any]]] = []

    class Config:
        schema_extra = {
            "example": {
                "message_id": "msg_123",
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "role": "user",
                "content": "What is company law?",
                "created_at": "2026-02-05T10:00:00Z",
                "metadata": {}
            }
        }


class ConversationHistoryResponse(BaseModel):
    """Full conversation with messages"""
    conversation: ConversationResponse
    messages: List[MessageResponse]
    summary: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "conversation": {
                    "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_id": "admin",
                    "title": "Company Law Discussion",
                    "message_count": 5,
                    "created_at": "2026-02-05T10:00:00Z",
                    "updated_at": "2026-02-05T12:30:00Z",
                    "is_deleted": False
                },
                "messages": [],
                "summary": "Discussion about Norwegian company law regulations"
            }
        }


# ============================================
# RESPONSE MODELS - EXISTING
# ============================================

class Source(BaseModel):
    """Source citation"""
    title: str = Field(..., description="Document title")
    url: str = Field(..., description="Lovdata URL")
    chunk_text: str = Field(..., description="Relevant text excerpt")
    relevance_score: float = Field(..., description="Similarity score")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ChatResponse(BaseModel):
    """Chat response with RAG"""
    answer: str = Field(..., description="Generated answer")
    sources: List[Source] = Field(default_factory=list, description="Source citations")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Response metadata")
    conversation_id: Optional[str] = Field(None, description="Conversation ID")
    message_id: Optional[str] = Field(None, description="Message ID")

    class Config:
        schema_extra = {
            "example": {
                "answer": "Aksjeselskap i Norge reguleres av aksjeloven...",
                "sources": [
                    {
                        "title": "Aksjeloven",
                        "url": "https://lovdata.no/dokument/NL/lov/1997-06-13-44",
                        "chunk_text": "§ 1-1. Aksjeselskap er en juridisk person...",
                        "relevance_score": 0.92,
                        "metadata": {
                            "file_name": "nl-19970613-044.xml",
                            "chunk_index": 0,
                        },
                    }
                ],
                "metadata": {
                    "query_time": 1.23,
                    "chunks_retrieved": 3,
                    "tokens_used": 450,
                    "cached": False,
                    "model": "gpt-4",
                },
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "message_id": "msg_456"
            }
        }


class SearchResult(BaseModel):
    """Single search result"""
    id: str = Field(..., description="Chunk ID")
    title: str = Field(..., description="Parent document title")
    content: str = Field(..., description="Chunk content")
    url: str = Field(..., description="Lovdata URL")
    score: float = Field(..., description="Similarity score")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Search response"""
    results: List[SearchResult] = Field(default_factory=list, description="Search results")
    total_found: int = Field(..., description="Total results found")
    query_time: float = Field(..., description="Query time in seconds")

    class Config:
        schema_extra = {
            "example": {
                "results": [
                    {
                        "id": "chunk_12345",
                        "title": "Aksjeloven",
                        "content": "§ 1-1. Aksjeselskap er en juridisk person...",
                        "url": "https://lovdata.no/dokument/NL/lov/1997-06-13-44",
                        "score": 0.89,
                        "metadata": {
                            "file_name": "nl-19970613-044.xml",
                            "chunk_index": 0,
                            "parent_type": "lov",
                        },
                    }
                ],
                "total_found": 10,
                "query_time": 0.45,
            }
        }


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="System status")
    version: str = Field(..., description="API version")
    milvus_connected: bool = Field(..., description="Milvus connection status")
    llm_connected: bool = Field(..., description="LLM service status")
    cache_connected: bool = Field(..., description="Cache service status")
    supabase_connected: bool = Field(default=False, description="Supabase connection status")
    total_queries: int = Field(default=0, description="Total queries processed")
    uptime: float = Field(default=0.0, description="Uptime in seconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "version": "2.0.0",
                "milvus_connected": True,
                "llm_connected": True,
                "cache_connected": True,
                "supabase_connected": True,
                "total_queries": 1250,
                "uptime": 86400.0,
                "timestamp": "2026-02-05T10:30:00Z",
            }
        }


# ============================================
# INTERNAL MODELS
# ============================================

class RetrievedChunk(BaseModel):
    """Internal model for retrieved chunks"""
    chunk_id: str
    file_name: str
    text: str
    parent_title: str
    parent_type: str
    chunk_index: int
    score: float
    embedding: Optional[List[float]] = None


class ContextMessage(BaseModel):
    """Message in context window"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime


class ContextWindow(BaseModel):
    """Conversation context for LLM"""
    messages: List[ContextMessage]
    summary: Optional[str] = None
    total_messages: int