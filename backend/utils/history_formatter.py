"""
utils/history_formatter.py — Shared Conversation History Formatter Utility
"""

from typing import Dict, List, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def convert_history_to_messages(
    conversation_history: Optional[List[Dict[str, str]]] = None,
    max_turns: Optional[int] = None,
) -> List[BaseMessage]:
    """
    Converts conversation history dictionary lists into LangChain Message objects.
    
    Args:
        conversation_history: List of {"role": "user"|"assistant", "content": "..."}
        max_turns: Optional limit for recent turns (e.g. 6)
    """
    messages: List[BaseMessage] = []
    if conversation_history:
        history_slice = conversation_history[-max_turns:] if max_turns else conversation_history
        for msg in history_slice:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
    return messages
