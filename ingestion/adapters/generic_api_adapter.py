"""
adapters/generic_api_adapter.py
================================
A flexible fallback adapter for REST APIs.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import requests

from ingestion.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class GenericApiAdapter(BaseAdapter):
    """Fallback adapter for generic REST APIs."""

    def get_source_name(self) -> str:
        return "generic_fallback"

    def fetch(self, input_path: Optional[str] = None) -> Any:
        base_url = self.config.get("base_url")
        if not base_url:
            logger.error("No base_url configured for GenericApiAdapter")
            return []

        method = self.config.get("method", "GET")
        headers = self.config.get("headers", {})

        # Merge input_path if it looks like an endpoint path
        url = base_url
        if input_path and not input_path.startswith("http"):
            url = f"{base_url.rstrip('/')}/{input_path.lstrip('/')}"
        elif input_path and input_path.startswith("http"):
            url = input_path

        logger.info("GenericApiAdapter fetching from: %s", url)
        
        try:
            response = requests.request(method, url, headers=headers, timeout=30)
            response.raise_for_status()
            
            if self.config.get("response_format") == "json":
                return response.json()
            return response.text
        except requests.RequestException as exc:
            logger.error("GenericApiAdapter request failed: %s", exc)
            return None

    def parse(self, raw_data: Any) -> List[Dict[str, Any]]:
        if not raw_data:
            return []

        # If it's a list of dicts, great
        if isinstance(raw_data, list) and all(isinstance(x, dict) for x in raw_data):
            return raw_data
            
        # If it's a single dict
        if isinstance(raw_data, dict):
            # Check if there's a list inside typical wrappers
            for key in ["data", "items", "results"]:
                if key in raw_data and isinstance(raw_data[key], list):
                    return raw_data[key]
            return [raw_data]

        # Raw text fallback
        return [{
            "raw_content": str(raw_data),
            "content": str(raw_data),
            "title": "API Response"
        }]
