"""
utils/context_builder.py — Reusable Context Builder Utility
"""

from typing import Dict, List, Optional


class ContextBuilder:
    """Builder class for constructing intent and conversation context strings."""

    def __init__(self) -> None:
        self._parts: List[str] = []

    def add_messages(self, history: Optional[List[Dict[str, str]]]) -> "ContextBuilder":
        if history:
            for m in history:
                if isinstance(m, dict) and m.get("content"):
                    role = m.get("role", "user").capitalize()
                    self._parts.append(f"{role}: {m['content']}")
        return self

    def add_query(self, query: str) -> "ContextBuilder":
        if query:
            self._parts.append(f"User: {query}")
        return self

    def build(self) -> str:
        return "\n".join(self._parts)
