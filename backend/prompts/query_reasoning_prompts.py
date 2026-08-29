"""
prompts/query_reasoning_prompts.py — Prompt loader for QueryReasoningAgent
"""

import os

_PATH = os.path.join(os.path.dirname(__file__), "query_reasoning_prompt.txt")

def get_query_reasoning_prompt() -> str:
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return (
            "You are a Norwegian Legal Statute Routing Specialist. "
            "Output valid JSON with keys: statute_id, statute_name, domain, jurisdiction, scope, b2b_b2c, response_style, enriched_query."
        )

QUERY_REASONING_SYSTEM_PROMPT = get_query_reasoning_prompt()
