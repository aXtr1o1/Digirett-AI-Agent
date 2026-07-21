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

            # Stem matching: split parenthetical context from the core term
            clean_term = re.sub(r"\(.*?\)", "", term).strip()
            term_words = re.findall(r"\b\w{3,}\b", clean_term)
            
            # Smart stemming to prevent short root-word collisions (e.g. "konkurs" vs "konkursbegjæring")
            def get_stem(word: str) -> str:
                if len(word) <= 6:
                    return word
                return word[:10]
                
            term_stems = {get_stem(w) for w in term_words}
            
            query_words = re.findall(r"\b\w{3,}\b", q_lower)
            query_stems = {get_stem(w) for w in query_words}

            # Check if all core term stems exist in query
            if term_stems and term_stems.issubset(query_stems):
                # If parenthetical context exists, check if at least one context stem matches the query
                paren_match = re.search(r"\((.*?)\)", term)
                if paren_match:
                    paren_words = re.findall(r"\b\w{3,}\b", paren_match.group(1))
                    paren_stems = {get_stem(w) for w in paren_words}
                    if paren_stems and not paren_stems.intersection(query_stems):
                        continue

                correct_route_str = confuser.get("correct_route", "")
                logger.info(
                    f"⚠️ Confuser hit: '{term}' matched query stems. "
                    f"Redirecting route from {subdomain_id} to '{correct_route_str}' | "
                    f"Reason: {confuser.get('reason')}"
                )
                
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
