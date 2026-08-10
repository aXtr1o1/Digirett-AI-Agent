"""
prompts/document_classifier_prompt.py — Prompt loader for DocumentClassifierAgent
"""

import os

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "document_classifier.txt")

def get_document_classifier_prompt() -> str:
    """Reads and returns the system prompt for DocumentClassifierAgent."""
    try:
        with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return (
            "You are a legal query classifier. Decide whether intent is DOCQA, LEGAL, HYBRID, or FOLLOWUP. "
            "Respond in JSON format: {\"intent\": \"<INTENT>\", \"reason\": \"<reason>\"}"
        )

DOCUMENT_CLASSIFIER_PROMPT = get_document_classifier_prompt()
