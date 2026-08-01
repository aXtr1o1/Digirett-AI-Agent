"""
router/alias_resolver.py — Dynamic Taxonomy Alias Resolver
"""

import logging
from typing import Dict, Optional
from router.taxonomy_loader import taxonomy_loader

logger = logging.getLogger(__name__)


class AliasResolver:

    @staticmethod
    def resolve(subdomain_id: str) -> str:
        if not subdomain_id:
            return ""

        alias_map = taxonomy_loader.get_aliases()
        curr = subdomain_id
        visited = set()

        while curr in alias_map and curr not in visited:
            visited.add(curr)
            canonical = alias_map[curr]
            logger.info(f"🔄 Alias hit: mapping subdomain '{curr}' to canonical '{canonical}'")
            curr = canonical

        return curr

    @staticmethod
    def validate_targets() -> bool:
        """Validate that all alias targets point to real subdomains."""
        alias_map = taxonomy_loader.get_aliases()
        valid_subs = set(taxonomy_loader.get_all_subdomains().keys())
        invalid_aliases = []

        for src, target in alias_map.items():
            if target not in valid_subs:
                invalid_aliases.append((src, target))

        if invalid_aliases:
            logger.warning(f"⚠️ Invalid alias targets detected: {invalid_aliases}")
            return False
        return True
