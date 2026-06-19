# backend/router/thin_pointer_resolver.py

import logging
from typing import List

logger = logging.getLogger(__name__)

class ThinPointerResolver:
    
    @staticmethod
    def resolve(subdomain_id: str) -> List[str]:
        """
        Resolves thin pointers to return all target subdomains that must be searched.
        """
        if subdomain_id == "MA-03":
            logger.info("📍 Thin pointer hit: subdomain 'MA-03' redirects to EL-04 (Arbeidsrett) + MA-03")
            return ["EL-04", "MA-03"]
            
        return [subdomain_id]
