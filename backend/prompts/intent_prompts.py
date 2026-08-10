"""
prompts/intent_prompts.py — Prompt loader for IntentAgent
"""

import os

_PATH = os.path.join(os.path.dirname(__file__), "intent_prompt.txt")

def get_intent_prompt() -> str:
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return (
            "Classify intent as CASUAL or LEGAL and detect language. "
            "Output JSON: {\"intent\": \"LEGAL\", \"language\": \"norwegian\"}"
        )

INTENT_SYSTEM_PROMPT = get_intent_prompt()
