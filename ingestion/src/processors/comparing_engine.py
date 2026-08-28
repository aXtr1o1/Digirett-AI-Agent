from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from ingestion.src.config import SUPABASE_BUCKET
from ingestion.src.storage.supabase_store import SupabaseStore

logger = logging.getLogger(__name__)


@dataclass
class ComparisonResult:
    """Encapsulates the differential comparison between live xAPI metadata and Supabase Bucket Ledger."""
    new_docs: List[Dict[str, Any]] = field(default_factory=list)
    modified_docs: List[Dict[str, Any]] = field(default_factory=list)
    unchanged_docs: List[Dict[str, Any]] = field(default_factory=list)
    deleted_doc_ids: List[str] = field(default_factory=list)
    total_evaluated: int = 0

    @property
    def has_changes(self) -> bool:
        return bool(self.new_docs or self.modified_docs or self.deleted_doc_ids)

    @property
    def target_doc_ids(self) -> List[str]:
        target_ids = []
        for d in self.new_docs + self.modified_docs:
            cid = d.get("canonical_document_id") or d.get("dok_id")
            if cid:
                target_ids.append(cid)
        return target_ids

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_evaluated": self.total_evaluated,
            "new_count": len(self.new_docs),
            "modified_count": len(self.modified_docs),
            "unchanged_count": len(self.unchanged_docs),
            "deleted_count": len(self.deleted_doc_ids),
            "total_to_process": len(self.new_docs) + len(self.modified_docs),
            "has_changes": self.has_changes,
        }


class ComparingEngine:

    def __init__(
        self,
        supabase_store: Optional[SupabaseStore] = None,
        bucket_name: Optional[str] = None,
        ledger_path: str = "ledger/ledger_manifest.json",
    ):
        self.supabase_store = supabase_store or SupabaseStore()
        self.bucket_name = bucket_name or SUPABASE_BUCKET
        self.ledger_path = ledger_path
        self._ledger_cache: Optional[Dict[str, Any]] = None

    def load_ledger(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Loads or initializes the master ledger JSON object from Supabase Storage."""
        if self._ledger_cache is None or force_refresh:
            self._ledger_cache = self.supabase_store.get_or_create_bucket_ledger(
                bucket_name=self.bucket_name,
                storage_path=self.ledger_path,
            )
        return self._ledger_cache

    def save_ledger(self, ledger_data: Optional[Dict[str, Any]] = None) -> bool:
        """Uploads updated ledger manifest JSON back to Supabase Storage."""
        data_to_save = ledger_data or self._ledger_cache
        if not data_to_save:
            return False

        data_to_save["last_synced_at"] = datetime.now(timezone.utc).isoformat()
        docs = data_to_save.get("documents", {})
        data_to_save["total_documents"] = len(docs)

        success = self.supabase_store.save_bucket_ledger(
            ledger_data=data_to_save,
            bucket_name=self.bucket_name,
            storage_path=self.ledger_path,
        )
        if success:
            self._ledger_cache = data_to_save
            logger.info("ComparingEngine: Ledger successfully synced to Supabase Storage (%d docs)", len(docs))
        return success

    def rebuild_ledger_from_db(self) -> Dict[str, Any]:
        """Rebuilds the ledger manifest from the PostgreSQL legal_documents table and uploads to Supabase Storage."""
        db_docs = self.supabase_store.get_document_ledger_from_db()
        ledger_obj = {
            "ledger_version": "2.0.0",
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
            "total_documents": len(db_docs),
            "documents": db_docs,
        }
        self.save_ledger(ledger_obj)
        logger.info("ComparingEngine: Ledger rebuilt from DB with %d documents and saved to storage.", len(db_docs))
        return ledger_obj

    def update_document_entry(
        self,
        doc_id: str,
        document_metadata: Dict[str, Any],
        vdb_status: str = "SYNCED",
    ) -> None:
        """Updates or adds a single document in the in-memory ledger cache."""
        ledger = self.load_ledger()
        if "documents" not in ledger:
            ledger["documents"] = {}

        now_iso = datetime.now(timezone.utc).isoformat()
        existing = ledger["documents"].get(doc_id, {})

        last_amended = (
            document_metadata.get("dato_sist_endret")
            or document_metadata.get("sist_endret_dato")
            or document_metadata.get("sist_endret")
            or document_metadata.get("last_amended_date")
            or document_metadata.get("dato")
            or existing.get("last_amended_date")
        )

        raw_fulltext = document_metadata.get("fulltekst") or document_metadata.get("content") or ""
        generated_hash = (
            hashlib.md5(raw_fulltext.encode("utf-8")).hexdigest()
            if raw_fulltext and isinstance(raw_fulltext, str) and raw_fulltext.strip()
            else None
        )

        content_hash = (
            document_metadata.get("fil_md5")
            or document_metadata.get("source_md5")
            or document_metadata.get("content_file_hash")
            or generated_hash
            or existing.get("content_file_hash")
        )

        ledger["documents"][doc_id] = {
            "canonical_document_id": doc_id,
            "dok_id": document_metadata.get("dok_id") or doc_id,
            "xapi_id": str(document_metadata.get("id") or document_metadata.get("xapi_id") or ""),
            "document_type": document_metadata.get("document_type", "LAW"),
            "title": document_metadata.get("title") or document_metadata.get("tittel") or document_metadata.get("short_title") or existing.get("title", "Untitled"),
            "last_amended_date": str(last_amended).strip() if last_amended else None,
            "paragraph_count": document_metadata.get("paragraph_count") or document_metadata.get("antall_paragrafer") or existing.get("paragraph_count", 0),
            "vdb_status": vdb_status,
            "content_file_hash": str(content_hash).strip() if content_hash else None,
            "last_synced_at": now_iso,
        }

    def remove_document_entry(self, doc_id: str) -> None:
        """Marks or removes a document from the ledger."""
        ledger = self.load_ledger()
        if "documents" in ledger and doc_id in ledger["documents"]:
            ledger["documents"][doc_id]["vdb_status"] = "DELETE_PENDING"
            ledger["documents"][doc_id]["is_active"] = False

    def compare(
        self,
        discovered_xapi_docs: List[Dict[str, Any]],
        detect_deletions: bool = False,
    ) -> ComparisonResult:
        """
        Compares live xAPI metadata documents against the Supabase Bucket Ledger.
        Returns a ComparisonResult containing new, modified, unchanged, and deleted documents.
        """
        ledger = self.load_ledger()
        tracked_docs: Dict[str, Dict[str, Any]] = ledger.get("documents", {})

        result = ComparisonResult()
        result.total_evaluated = len(discovered_xapi_docs)
        discovered_ids: Set[str] = set()

        for doc in discovered_xapi_docs:
            cid = doc.get("canonical_document_id") or doc.get("dok_id")
            if not cid:
                continue

            discovered_ids.add(cid)
            ledger_entry = tracked_docs.get(cid)

            if not ledger_entry:
                # 1. New Document
                result.new_docs.append(doc)
                continue

            # 2. Check for Modifications
            xapi_amended = str(
                doc.get("dato_sist_endret")
                or doc.get("sist_endret_dato")
                or doc.get("sist_endret")
                or doc.get("last_amended_date")
                or doc.get("dato")
                or ""
            ).strip()
            ledger_amended = str(
                ledger_entry.get("last_amended_date")
                or ledger_entry.get("dato_sist_endret")
                or ledger_entry.get("sist_endret_dato")
                or ledger_entry.get("sist_endret")
                or ""
            ).strip()

            doc_fulltext = doc.get("fulltekst") or doc.get("content") or ""
            doc_gen_hash = (
                hashlib.md5(doc_fulltext.encode("utf-8")).hexdigest()
                if doc_fulltext and isinstance(doc_fulltext, str) and doc_fulltext.strip()
                else ""
            )

            xapi_hash = str(
                doc.get("fil_md5")
                or doc.get("source_md5")
                or doc.get("content_file_hash")
                or doc_gen_hash
                or ""
            ).strip()
            ledger_hash = str(
                ledger_entry.get("content_file_hash")
                or ledger_entry.get("fil_md5")
                or ledger_entry.get("source_md5")
                or ""
            ).strip()

            xapi_count = doc.get("antall_paragrafer") or doc.get("paragraph_count")
            ledger_count = ledger_entry.get("paragraph_count") or ledger_entry.get("antall_paragrafer")

            vdb_status = ledger_entry.get("vdb_status", "PENDING")

            is_modified = False
            if vdb_status != "SYNCED":
                is_modified = True
            elif xapi_hash and ledger_hash and xapi_hash != ledger_hash:
                is_modified = True
            elif xapi_amended and ledger_amended and xapi_amended != ledger_amended:
                is_modified = True
            elif xapi_count is not None and ledger_count is not None and int(xapi_count) != int(ledger_count):
                is_modified = True

            if is_modified:
                result.modified_docs.append(doc)
            else:
                result.unchanged_docs.append(doc)

        # 3. Detect Deletions / Repeals
        if detect_deletions and len(discovered_ids) > 0:
            for tracked_id, entry in tracked_docs.items():
                if tracked_id not in discovered_ids and entry.get("vdb_status") != "DELETE_PENDING":
                    result.deleted_doc_ids.append(tracked_id)

        summary = result.get_summary()
        logger.info(
            "ComparingEngine Result | Evaluated: %d | New: %d | Modified: %d | Unchanged: %d | Deleted: %d",
            summary["total_evaluated"],
            summary["new_count"],
            summary["modified_count"],
            summary["unchanged_count"],
            summary["deleted_count"],
        )
        return result
