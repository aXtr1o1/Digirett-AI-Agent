# backend/router/query_normalizer.py

import re
from typing import List

class QueryNormalizer:
    
    @staticmethod
    def normalize(text: str) -> List[str]:
        if not text:
            return []
        
        # Lowercase
        normalized = text.lower()
        
        # Replace common punctuation with space
        normalized = re.sub(r"[^\w\s\-\u00E6\u00F8\u00E5\u00C6\u00D8\u00C5]", " ", normalized)
        
        # Tokenize by whitespace
        tokens = [t.strip() for t in normalized.split() if t.strip()]
        return tokens

    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""
        return " ".join(QueryNormalizer.normalize(text))
