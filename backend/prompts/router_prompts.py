"""
prompts/router_prompts.py — Prompt loader for RouterAgent
"""

import os

_PATH = os.path.join(os.path.dirname(__file__), "router_prompt.txt")

def get_router_prompt() -> str:
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return (
            "You are a Legal Query Routing Engine for Norwegian law. "
            "Output valid JSON with domain, subdomain_candidates, b2b_b2c, relationship_type, jurisdiction, matched_keywords, conflict_detected, and confidence."
        )

ROUTER_BASE_PROMPT = get_router_prompt()
