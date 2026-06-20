# backend/router/alias_resolver.py

import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Map of alias subdomains to canonical subdomains
_ALIAS_MAP: Dict[str, str] = {
    "MO-04": "DC-04",  # MO-04 (Limitation of claims in Monetary Claims) -> ALIAS of DC-04 (Limitation of claims in Debt Collection)
}

class AliasResolver:
    
    @staticmethod
    def resolve(subdomain_id: str) -> str:
        if subdomain_id in _ALIAS_MAP:
            canonical_id = _ALIAS_MAP[subdomain_id]
            logger.info(f"🔄 Alias hit: mapping subdomain '{subdomain_id}' to canonical '{canonical_id}'")
            return canonical_id
        return subdomain_id
