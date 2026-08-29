import hashlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DOMAIN_MATCH_BOOST = 1.03


class ResultMerger:

    @staticmethod
    def merge(
        results: List[Dict[str, Any]],
        target_domain: Optional[str] = None,
        strategy: str = "highest_score",
    ) -> List[Dict[str, Any]]:
        if not results:
            return []
        prepared: List[Dict[str, Any]] = []
        target_dom_lower = (target_domain or "").lower().strip()

        for raw in results:
            r = dict(raw)
            if target_dom_lower:
                chunk_dom = (
                    r.get("domain")
                    or r.get("domain_name")
                    or r.get("domain_id")
                    or ""
                )
                chunk_dom_lower = str(chunk_dom).lower().strip()
                if chunk_dom_lower and chunk_dom_lower == target_dom_lower:
                    r["score"] = float(r.get("score", 0.0)) * DOMAIN_MATCH_BOOST
                    r["domain_match_boost"] = True
                else:
                    r["domain_match_boost"] = False
            prepared.append(r)

        results = prepared

        # Step 1: Deduplicate by chunk_id using SHA-256 fallback hash.
        chunk_map: Dict[str, Dict[str, Any]] = {}
        for r in results:
            cid = r.get("chunk_id")
            if not cid:
                text_content = str(r.get("text", ""))
                cid = hashlib.sha256(
                    text_content.encode("utf-8")
                ).hexdigest()[:16]

            score = float(r.get("score", 0.0))
            if cid not in chunk_map:
                chunk_map[cid] = dict(r)
                chunk_map[cid]["merged_from"] = [r.get("chunk_id") or cid]
            else:
                existing = chunk_map[cid]
                existing["merged_from"].append(r.get("chunk_id") or cid)
                if (
                    strategy == "highest_score"
                    and score > float(existing.get("score", 0.0))
                ):
                    # Preserve the complete better row, not only its score.
                    merged_from = existing["merged_from"]
                    chunk_map[cid] = dict(r)
                    chunk_map[cid]["merged_from"] = merged_from

        unique_chunks = list(chunk_map.values())

        # Step 2: Deduplicate by citation reference key.
        citation_map: Dict[str, Dict[str, Any]] = {}
        for chunk in unique_chunks:
            url = (
                chunk.get("source_doc_url")
                or chunk.get("source_url")
                or chunk.get("url")
                or ""
            )
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
                citation_key = hashlib.sha256(
                    text_content.encode("utf-8")
                ).hexdigest()[:16]

            score = float(chunk.get("score", 0.0))
            if (
                citation_key not in citation_map
                or score > float(citation_map[citation_key].get("score", 0.0))
            ):
                citation_map[citation_key] = chunk

        merged = list(citation_map.values())
        merged.sort(
            key=lambda x: float(x.get("score", 0.0)),
            reverse=True,
        )

        logger.info(
            "Merged %s chunks -> %s unique citations "
            "(strategy=%s, domain_policy=soft_boost)",
            len(results),
            len(merged),
            strategy,
        )
        return merged
