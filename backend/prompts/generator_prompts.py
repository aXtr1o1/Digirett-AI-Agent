"""
prompts/generator_prompts.py — Prompt loader for GeneratorAgent
"""

import os

_DIR = os.path.dirname(__file__)

def _read(name: str, fallback: str) -> str:
    try:
        with open(os.path.join(_DIR, name), "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return fallback

CASUAL_SYSTEM_PROMPT = _read(
    "casual_prompt.txt",
    "You are a friendly, helpful AI assistant. Keep responses brief and friendly."
)

LEGAL_SYSTEM_PROMPT = _read(
    "legal_prompt.txt",
    "You are an AI Legal Assistant specialized in Norwegian law. Answer from provided sources. Prepend [SCORE:x.x] on line 1."
)
