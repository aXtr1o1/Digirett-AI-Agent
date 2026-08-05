"""
utils/json_response_parser.py — Centralized JSON Response Parser Utility
"""

import json
import logging
from typing import Any, Dict, Optional

try:
    import json_repair
except ImportError:
    json_repair = None

logger = logging.getLogger(__name__)


def parse_json_response(raw_text: str) -> Optional[Dict[str, Any]]:
    if not raw_text or not isinstance(raw_text, str):
        return None

    cleaned = raw_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # 1. Standard json.loads
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. json_repair fallback
    if json_repair is not None:
        try:
            data = json_repair.loads(cleaned)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 3. Substring extract fallback (first '{' to last '}')
    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            sub = cleaned[start : end + 1]
            data = json.loads(sub)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.warning(f" JSON parsing fallback failed: {exc}")

    return None
