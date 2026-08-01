"""
agents/memory_agent.py — Backward Compatibility Wrapper

Imports and exposes ConversationMemoryService as MemoryAgent for backward compatibility.
"""

from services.memory_service import ConversationMemoryService, MemoryAgent

__all__ = ["ConversationMemoryService", "MemoryAgent"]