"""
prompts/document_qa_prompts.py — Prompt loader for DocumentQAAgent
"""

import os

_DIR = os.path.dirname(__file__)
_DOCQA_PATH = os.path.join(_DIR, "docqa_prompt.txt")
_HYBRID_PATH = os.path.join(_DIR, "hybrid_prompt.txt")


def _read_prompt(path: str, fallback: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return fallback


DOCQA_SYSTEM_PROMPT = _read_prompt(
    _DOCQA_PATH,
    "You are a document analysis assistant. Answer ONLY from DOCUMENT TEXT. Append [SCORE:x.x] on the last line."
)

HYBRID_SYSTEM_PROMPT = _read_prompt(
    _HYBRID_PATH,
    "You are a legal document compliance assistant. Cross-reference DOCUMENT TEXT and LEGAL SOURCES. Append [SCORE:x.x] on the last line."
)
