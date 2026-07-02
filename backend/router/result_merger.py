# backend/router/result_merger.py

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ResultMerger:
    
    @staticmethod
    def merge(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merges results from multiple retrieval queries.
        Deduplicates by chunk_id and keeps the one with the highest score.
        Deduplicates by source_doc_url + section_ref to maximize coverage.
        """
        if not results:
            return []

        # Step 1: Deduplicate by chunk_id, keeping highest score
        chunk_map: Dict[str, Dict[str, Any]] = {}
        for r in results:
            cid = r.get("chunk_id")
            if not cid:
                # Fallback to text hash if chunk_id is missing
                cid = str(hash(r.get("text", "")))
            
            score = r.get("score", 0.0)
            if cid not in chunk_map or score > chunk_map[cid].get("score", 0.0):
                chunk_map[cid] = r

        unique_chunks = list(chunk_map.values())

        # Step 2: Deduplicate by source_doc_url + section_ref
        # Keep the chunk with the highest score for any duplicate source-section reference.
        citation_map: Dict[str, Dict[str, Any]] = {}
        for chunk in unique_chunks:
            url = chunk.get("source_doc_url") or chunk.get("url") or ""
            sec = chunk.get("section_ref") or ""
            
            # Key identifier for unique law section
            citation_key = f"{url}#{sec}" if sec else url
            if not citation_key:
                # If both are empty, do not deduplicate
                citation_key = str(hash(chunk.get("text", "")))
                
            score = chunk.get("score", 0.0)
            if citation_key not in citation_map or score > citation_map[citation_key].get("score", 0.0):
                citation_map[citation_key] = chunk

        merged = list(citation_map.values())
        
        # Sort by score descending
        merged.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        
        logger.info(f"🥞 Merged {len(results)} chunks -> {len(merged)} unique citations")
        return merged
