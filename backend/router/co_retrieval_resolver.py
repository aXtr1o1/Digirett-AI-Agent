# backend/router/co_retrieval_resolver.py

import logging
from typing import List, Set
from router.taxonomy_loader import taxonomy_loader

logger = logging.getLogger(__name__)

class CoRetrievalResolver:
    
    @staticmethod
    def get_targets(subdomain_ids: List[str], query_text: str) -> List[str]:
        """
        Determines the complete set of subdomains to search based on the initial
        subdomains resolved and any co-retrieval rules.
        """
        final_targets: Set[str] = set()
        q_lower = query_text.lower()

        for sub_id in subdomain_ids:
            final_targets.add(sub_id)

            # 1. Fetch dynamic co-retrieval from taxonomy JSON if present
            sub_data = taxonomy_loader.get_subdomain(sub_id)
            if sub_data:
                co_ret = sub_data.get("co_retrieval", {})
                if co_ret and isinstance(co_ret, dict):
                    paired = co_ret.get("paired_with", [])
                    if paired:
                        logger.info(f"🔗 Co-retrieval match from JSON: subdomain '{sub_id}' paired with {paired}")
                        for p in paired:
                            final_targets.add(p)

            # 2. PDF Rule 2: "varen var defekt" + time element -> OB-01 + OB-02
            if sub_id == "OB-01":
                time_keywords = ["tid", "dager", "måneder", "år", "senere", "time", "days", "months", "years", "late", "sent"]
                if any(kw in q_lower for kw in time_keywords):
                    logger.info("🔗 Co-retrieval hit (PDF Rule 2): 'OB-01' + time element -> adding 'OB-02'")
                    final_targets.add("OB-02")

            # 3. PDF Rule 3: "hva skjer med ansatte ved fusjon" -> MA-03 (pointer) -> EL-04 + MA-01
            if sub_id == "MA-03":
                logger.info("🔗 Co-retrieval hit (PDF Rule 3): 'MA-03' pointer -> adding 'EL-04' and 'MA-01'")
                final_targets.add("EL-04")
                final_targets.add("MA-01")

        return list(final_targets)
