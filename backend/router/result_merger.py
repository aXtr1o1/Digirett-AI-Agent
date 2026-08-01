"""
router/result_merger.py — Deterministic Chunk Result Merger & Provenance Engine
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ResultMerger:

    @staticmethod
    def merge(
        results: List[Dict[str, Any]],
        target_domain: Optional[str] = None,
        strategy: str = "highest_score",
    ) -> List[Dict[str, Any]]:
        if not results:
            return []

        # Step 0: Domain validation filter
        if target_domain:
            target_dom_lower = target_domain.lower().strip()
            filtered_results = []
            for r in results:
                chunk_dom = (r.get("domain") or "").lower().strip()
                if not chunk_dom or chunk_dom == target_dom_lower:
                    filtered_results.append(r)
                else:
                    logger.debug(f"ResultMerger: Filtering out chunk with domain '{chunk_dom}' != target '{target_dom_lower}'")
            results = filtered_results if filtered_results else results

        # Step 1: Deduplicate by chunk_id using SHA-256 fallback hash
        chunk_map: Dict[str, Dict[str, Any]] = {}
        for r in results:
            cid = r.get("chunk_id")
            if not cid:
                text_content = str(r.get("text", ""))
                cid = hashlib.sha256(text_content.encode("utf-8")).hexdigest()[:16]

            score = float(r.get("score", 0.0))
            if cid not in chunk_map:
                chunk_map[cid] = dict(r)
                chunk_map[cid]["merged_from"] = [r.get("chunk_id") or cid]
            else:
                existing = chunk_map[cid]
                existing["merged_from"].append(r.get("chunk_id") or cid)
                if strategy == "highest_score" and score > float(existing.get("score", 0.0)):
                    chunk_map[cid]["score"] = score

        unique_chunks = list(chunk_map.values())

        # Step 2: Deduplicate by citation reference key
        citation_map: Dict[str, Dict[str, Any]] = {}
        for chunk in unique_chunks:
            url = chunk.get("source_doc_url") or chunk.get("url") or ""
            sec = chunk.get("section_ref") or ""
            para = chunk.get("paragraph") or ""

            if sec and para:
                citation_key = f"{url}#{sec}({para})"
            elif sec:
                citation_key = f"{url}#{sec}"
            else:
                citation_key = url

            if not citation_key:
                text_content = str(chunk.get("text", ""))
                citation_key = hashlib.sha256(text_content.encode("utf-8")).hexdigest()[:16]

            score = float(chunk.get("score", 0.0))
            if citation_key not in citation_map or score > float(citation_map[citation_key].get("score", 0.0)):
                citation_map[citation_key] = chunk

        merged = list(citation_map.values())
        merged.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)

        logger.info(f"🥞 Merged {len(results)} chunks -> {len(merged)} unique citations (strategy={strategy})")
        return merged
