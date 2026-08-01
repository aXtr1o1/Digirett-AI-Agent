"""
prompts/user_memory_prompts.py — Prompt loader for UserMemoryAgent
"""

import os

_PATH = os.path.join(os.path.dirname(__file__), "user_memory_prompt.txt")

def get_user_memory_prompt() -> str:
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return (
            "You are a memory extraction assistant. Output ONLY JSON array of objects with keys 'fact' and 'confidence'."
        )

USER_MEMORY_SYSTEM_PROMPT = get_user_memory_prompt()
