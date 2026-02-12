from pydantic import BaseModel, Field
from typing import Dict, Any
from datetime import datetime


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=20000)
    top_k: int = Field(default=3, ge=1, le=10)
    include_sources: bool = Field(default=True)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
