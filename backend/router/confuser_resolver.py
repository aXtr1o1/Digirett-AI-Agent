# backend/router/confuser_resolver.py

import logging
from typing import Optional, Dict, Any
from router.taxonomy_loader import taxonomy_loader

logger = logging.getLogger(__name__)

class ConfuserResolver:
    
    @staticmethod
    def resolve(subdomain_id: str, query_text: str) -> str:
        """
        Checks if the query matches any of the subdomain's confuser terms.
        If matched, redirects to the correct subdomain route.
        """
        sub_data = taxonomy_loader.get_subdomain(subdomain_id)
        if not sub_data:
            return subdomain_id

        confusers = sub_data.get("confusers", [])
        if not confusers:
            return subdomain_id

        q_lower = query_text.lower()

        for confuser in confusers:
            term = confuser.get("term", "").lower()
            if not term:
                continue

            # Substring match on the confuser term
            if term in q_lower:
                correct_route_str = confuser.get("correct_route", "")
                logger.info(
                    f"⚠️ Confuser hit: '{term}' in query. "
                    f"Redirecting route from {subdomain_id} to '{correct_route_str}' | "
                    f"Reason: {confuser.get('reason')}"
                )
                
                # Parse the target subdomain ID from the correct_route string
                # Example: "D02_MA / Merger Process" or "D07_INSOLVENCY / IN-04" or "CL-02"
                resolved_id = ConfuserResolver._parse_subdomain_id(correct_route_str)
                if resolved_id:
                    return resolved_id

        return subdomain_id

    @staticmethod
    def _parse_subdomain_id(route_str: str) -> Optional[str]:
        if not route_str:
            return None
        
        # Check for standard subdomain codes (e.g. CY-01, CL-02, EL-04, etc.)
        # Match using regex pattern: two uppercase letters followed by a dash and two digits
        match = re.search(r"\b([A-Z]{2}-\d{2})\b", route_str)
        if match:
            return match.group(1)
            
        # Try splitting by slashes or spaces
        parts = route_str.replace("/", " ").split()
        for p in parts:
            p_strip = p.strip().upper()
            # If matches domain key or subdomain code
            if len(p_strip) == 5 and p_strip[2] == "-":
                return p_strip
                
        return None

# Import re in module since we reference it in _parse_subdomain_id
import re
