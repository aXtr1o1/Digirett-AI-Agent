"""
router/utils/models.py — Structured Output Models for Router Components
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RoutingDecision(BaseModel):
    route: str
    reason: str
    confidence: float = 1.0
    matched_term: Optional[str] = None


class ResolvedRoute(BaseModel):
    route: str
    reason: str
    matched_term: Optional[str] = None


class PointerResult(BaseModel):
    targets: List[str]
    pointer_type: str = "direct"
