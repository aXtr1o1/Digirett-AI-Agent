"""
router/thin_pointer_resolver.py — Dynamic Thin Pointer Resolver
"""

import logging
from typing import List, Set
from router.taxonomy_loader import taxonomy_loader
from router.utils.models import PointerResult

logger = logging.getLogger(__name__)


class ThinPointerResolver:

    @staticmethod
    def resolve(subdomain_id: str) -> List[str]:
        res = ThinPointerResolver.resolve_detailed(subdomain_id)
        return res.targets

    @staticmethod
    def resolve_detailed(subdomain_id: str) -> PointerResult:
        if not subdomain_id:
            return PointerResult(targets=[])

        targets: List[str] = [subdomain_id]
        visited: Set[str] = {subdomain_id}
        queue: List[str] = [subdomain_id]
        pointer_type = "direct"

        while queue:
            curr = queue.pop(0)
            sub_data = taxonomy_loader.get_subdomain(curr)
            if not sub_data:
                continue

            pointers = sub_data.get("thin_pointers", [])
            # Fallback legacy hardcoded MA-03 -> EL-04 check
            if curr == "MA-03" and "EL-04" not in pointers:
                pointers.append("EL-04")

            if pointers:
                pointer_type = "employment_bridge" if "EL-04" in pointers else "subdomain_pointer"

            for ptr in pointers:
                if ptr not in visited:
                    visited.add(ptr)
                    targets.append(ptr)
                    queue.append(ptr)
                    logger.info(f"📍 Thin pointer hit: '{curr}' -> adding '{ptr}'")

        return PointerResult(targets=targets, pointer_type=pointer_type)

    @staticmethod
    def validate_pointers() -> bool:
        valid_subs = set(taxonomy_loader.get_all_subdomains().keys())
        invalid_pointers = []
        for sub_id, sub_data in taxonomy_loader.get_all_subdomains().items():
            for ptr in sub_data.get("thin_pointers", []):
                if ptr not in valid_subs:
                    invalid_pointers.append((sub_id, ptr))
        if invalid_pointers:
            logger.warning(f"⚠️ Invalid thin pointer targets detected: {invalid_pointers}")
            return False
        return True
