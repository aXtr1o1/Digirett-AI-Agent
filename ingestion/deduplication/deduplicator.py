from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from ingestion.deduplication.hash_utils import compute_content_hash

logger = logging.getLogger(__name__)


def law_canonical_id(record: Dict[str, Any]) -> str:
    dok = str(record.get("dok_id") or record.get("id") or "").strip()
    return dok


def regulation_canonical_id(record: Dict[str, Any]) -> str:
    dok = record.get("dok_id")
    if dok and str(dok).strip():
        return str(dok).strip()
    sf = record.get("sf_dok_id")
    if sf and str(sf).strip():
        return str(sf).strip()
    raw_id = record.get("id")
    if raw_id is not None and str(raw_id).strip():
        return str(raw_id).strip()
    return ""


class CanonicalDeduplicator:
    """Handles canonical identity deduplication and provenance merging for laws and regulations."""

    def __init__(self):
        self.laws_by_canonical_id: Dict[str, Dict[str, Any]] = {}
        self.regulations_by_canonical_id: Dict[str, Dict[str, Any]] = {}

    def deduplicate_laws(self, raw_laws: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for item in raw_laws:
            dok_id = law_canonical_id(item)
            if not dok_id:
                continue

            domain_id = item.get("domain_id")
            candidate_domains = item.get("candidate_domain_ids") or ([domain_id] if domain_id else [])
            rettsomrade = item.get("rettsomrade_filter")

            if dok_id not in self.laws_by_canonical_id:
                canonical = dict(item)
                canonical["canonical_document_id"] = dok_id
                canonical["candidate_domain_ids"] = list(candidate_domains)
                canonical["matched_rettsomrader"] = [rettsomrade] if rettsomrade else []
                self.laws_by_canonical_id[dok_id] = canonical
            else:
                existing = self.laws_by_canonical_id[dok_id]
                for d in candidate_domains:
                    if d and d not in existing["candidate_domain_ids"]:
                        existing["candidate_domain_ids"].append(d)
                if rettsomrade and rettsomrade not in existing["matched_rettsomrader"]:
                    existing["matched_rettsomrader"].append(rettsomrade)

        logger.info("Law Deduplication: Processed %d domain appearances -> %d unique laws",
                    len(raw_laws), len(self.laws_by_canonical_id))
        return list(self.laws_by_canonical_id.values())

    def deduplicate_regulations(
        self,
        central_regs: List[Dict[str, Any]],
        linked_regs: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        if linked_regs is None:
            linked_regs = []

        # Process Central Regulations
        for reg in central_regs:
            canon_id = regulation_canonical_id(reg)
            if not canon_id:
                continue

            domain_id = reg.get("domain_id")
            candidate_domains = reg.get("candidate_domain_ids") or ([domain_id] if domain_id else [])
            rettsomrade = reg.get("rettsomrade_filter")

            if canon_id not in self.regulations_by_canonical_id:
                canonical = dict(reg)
                canonical["canonical_id"] = canon_id
                canonical["discovered_via"] = ["CENTRAL_RETTSOMRADE"]
                canonical["candidate_domain_ids"] = list(candidate_domains)
                canonical["matched_rettsomrader"] = [rettsomrade] if rettsomrade else []
                canonical["linked_law_ids"] = []
                self.regulations_by_canonical_id[canon_id] = canonical
            else:
                existing = self.regulations_by_canonical_id[canon_id]
                if "CENTRAL_RETTSOMRADE" not in existing["discovered_via"]:
                    existing["discovered_via"].append("CENTRAL_RETTSOMRADE")
                for d in candidate_domains:
                    if d and d not in existing["candidate_domain_ids"]:
                        existing["candidate_domain_ids"].append(d)
                if rettsomrade and rettsomrade not in existing["matched_rettsomrader"]:
                    existing["matched_rettsomrader"].append(rettsomrade)

        # Process Law-Linked Regulations
        for reg in linked_regs:
            canon_id = regulation_canonical_id(reg)
            if not canon_id:
                continue

            linked_law = reg.get("linked_from_law_dok_id")
            domain_id = reg.get("domain_id")
            candidate_domains = reg.get("candidate_domain_ids") or ([domain_id] if domain_id else [])

            if canon_id not in self.regulations_by_canonical_id:
                canonical = dict(reg)
                canonical["canonical_id"] = canon_id
                canonical["discovered_via"] = ["LAW_LINK"]
                canonical["candidate_domain_ids"] = list(candidate_domains)
                canonical["matched_rettsomrader"] = []
                canonical["linked_law_ids"] = [linked_law] if linked_law else []
                self.regulations_by_canonical_id[canon_id] = canonical
            else:
                existing = self.regulations_by_canonical_id[canon_id]
                if "LAW_LINK" not in existing["discovered_via"]:
                    existing["discovered_via"].append("LAW_LINK")
                if linked_law and linked_law not in existing["linked_law_ids"]:
                    existing["linked_law_ids"].append(linked_law)
                for d in candidate_domains:
                    if d and d not in existing["candidate_domain_ids"]:
                        existing["candidate_domain_ids"].append(d)

        logger.info("Regulation Deduplication: Central (%d) + Linked (%d) -> %d unique regulations",
                    len(central_regs), len(linked_regs), len(self.regulations_by_canonical_id))
        return list(self.regulations_by_canonical_id.values())


class Deduplicator:
    """Compatibility wrapper used by the legacy ingestion pipeline.

    Keeps the older document-level API (`check(doc)`) while delegating canonical
    deduplication to the newer ingestion deduplication module.
    """

    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name
        self._seen_doc_ids: Dict[str, str] = {}
        self._seen_content_hashes: Dict[str, str] = {}

    def _extract_doc_id(self, doc: Dict[str, Any]) -> str:
        return (
            str(doc.get("doc_id") or doc.get("dok_id") or doc.get("source_id") or "").strip()
            or str((doc.get("metadata") or {}).get("dok_id") or "").strip()
        )

    def _extract_content(self, doc: Dict[str, Any]) -> str:
        content = doc.get("content") or ""
        if isinstance(content, str):
            return content
        raw_data = doc.get("raw_data") or {}
        if isinstance(raw_data, dict):
            paragraphs = raw_data.get("paragraphs") or []
            if isinstance(paragraphs, list):
                parts = []
                for p in paragraphs:
                    if isinstance(p, dict):
                        text = p.get("content_text") or p.get("text") or ""
                        if text:
                            parts.append(str(text))
                if parts:
                    return "\n".join(parts)
        return ""

    def check(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Mark duplicates by document ID and content hash, while preserving the doc payload."""
        doc = dict(doc)
        doc_id = self._extract_doc_id(doc)
        content = self._extract_content(doc)
        content_hash = compute_content_hash(content) if content else ""

        is_duplicate = False
        duplicate_reason = None

        if doc_id:
            if doc_id in self._seen_doc_ids:
                is_duplicate = True
                duplicate_reason = "dok_id"
            else:
                self._seen_doc_ids[doc_id] = doc_id

        if not is_duplicate and content_hash:
            if content_hash in self._seen_content_hashes:
                is_duplicate = True
                duplicate_reason = "content_hash"
            else:
                self._seen_content_hashes[content_hash] = doc_id or content_hash

        doc["is_duplicate"] = bool(is_duplicate)
        doc["duplicate_reason"] = duplicate_reason
        if is_duplicate:
            doc["duplicate_score"] = 1.0
        else:
            doc["duplicate_score"] = 0.0

        return doc


__all__ = [
    "CanonicalDeduplicator",
    "Deduplicator",
    "law_canonical_id",
    "regulation_canonical_id",
]