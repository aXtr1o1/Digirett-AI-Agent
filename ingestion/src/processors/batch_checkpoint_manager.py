from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ingestion.src.config import CHECKPOINT_DIR

logger = logging.getLogger(__name__)


class BatchCheckpointManager:
    def __init__(self, checkpoint_dir: Optional[Path] = None, run_id: Optional[str] = None):
        self.checkpoint_dir = checkpoint_dir or CHECKPOINT_DIR
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_file = self.checkpoint_dir / "batch_manifest.json"
        self.run_id = run_id or f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        self._manifest_cache: Optional[Dict[str, Any]] = None

    def _atomic_write_json(self, target_path: Path, data: Dict[str, Any]) -> None:
        """Writes JSON to a temporary file first and replaces atomically to prevent corruption."""
        temp_path = target_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_path.replace(target_path)

    def load_manifest(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Loads or initializes the master batch manifest."""
        if self._manifest_cache is None or force_refresh:
            if self.manifest_file.exists():
                try:
                    with open(self.manifest_file, "r", encoding="utf-8") as f:
                        self._manifest_cache = json.load(f)
                except Exception as exc:
                    logger.warning("Could not read batch_manifest.json (%s), starting fresh.", exc)
                    self._manifest_cache = None

            if not self._manifest_cache:
                self._manifest_cache = {
                    "manifest_version": "2.0.0",
                    "run_id": self.run_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "last_updated_at": datetime.now(timezone.utc).isoformat(),
                    "total_batches": 0,
                    "completed_batches": 0,
                    "batches": {},
                    "global_committed_doc_ids": [],
                }
                self._atomic_write_json(self.manifest_file, self._manifest_cache)
        return self._manifest_cache

    def save_manifest(self) -> None:
        """Saves current manifest state to disk."""
        if self._manifest_cache:
            self._manifest_cache["last_updated_at"] = datetime.now(timezone.utc).isoformat()
            self._atomic_write_json(self.manifest_file, self._manifest_cache)

    def get_committed_doc_ids(self) -> Set[str]:
        """Returns the set of all document IDs that have already been committed in any batch."""
        manifest = self.load_manifest()
        return set(manifest.get("global_committed_doc_ids", []))

    def filter_unprocessed_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Cross-Batch Deduplication Gate:
        Filters out any document that has already been completed in an earlier committed batch.
        """
        committed_ids = self.get_committed_doc_ids()
        if not committed_ids:
            return documents

        unprocessed = []
        for doc in documents:
            cid = doc.get("canonical_document_id") or doc.get("dok_id")
            if cid and cid in committed_ids:
                continue
            unprocessed.append(doc)

        skipped_count = len(documents) - len(unprocessed)
        if skipped_count > 0:
            logger.info("BatchCheckpointManager: Deduplication skipped %d already-committed documents", skipped_count)
        return unprocessed

    def partition_into_batches(self, documents: List[Dict[str, Any]], batch_size: int = 50) -> List[List[Dict[str, Any]]]:
        """Partitions documents into discrete batches."""
        if batch_size <= 0:
            batch_size = 50
        return [documents[i : i + batch_size] for i in range(0, len(documents), batch_size)]

    def get_batch_checkpoint_path(self, batch_index: int) -> Path:
        """Returns file path for a specific batch checkpoint JSON (e.g. checkpoint_batch_001.json)."""
        return self.checkpoint_dir / f"checkpoint_batch_{batch_index:03d}.json"

    def is_batch_committed(self, batch_index: int) -> bool:
        """Checks if a batch has already been committed successfully."""
        manifest = self.load_manifest()
        batch_id = f"batch_{batch_index:03d}"
        batch_info = manifest.get("batches", {}).get(batch_id)
        if batch_info and batch_info.get("status") == "COMMITTED":
            checkpoint_file = self.get_batch_checkpoint_path(batch_index)
            return checkpoint_file.exists()
        return False

    def load_batch_checkpoint(self, batch_index: int) -> Optional[Dict[str, Any]]:
        """Loads a specific batch checkpoint JSON."""
        cp_path = self.get_batch_checkpoint_path(batch_index)
        if cp_path.exists():
            try:
                with open(cp_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning("Could not read %s: %s", cp_path.name, exc)
        return None

    def commit_batch(
        self,
        batch_index: int,
        total_batches: int,
        documents: List[Dict[str, Any]],
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        batch_id = f"batch_{batch_index:03d}"
        cp_path = self.get_batch_checkpoint_path(batch_index)

        doc_records: Dict[str, Dict[str, Any]] = {}
        new_doc_ids: List[str] = []

        for doc in documents:
            cid = doc.get("canonical_document_id") or doc.get("dok_id")
            if not cid:
                continue
            new_doc_ids.append(cid)
            doc_records[cid] = {
                "canonical_document_id": cid,
                "dok_id": doc.get("dok_id") or cid,
                "document_type": doc.get("document_type", "LAW"),
                "title": doc.get("title") or doc.get("tittel") or "Untitled",
                "paragraph_count": doc.get("paragraph_count", 0),
                "milvus_status": "INDEXED",
                "supabase_status": "COMMITTED",
                "processed_at": now_iso,
            }

        batch_checkpoint_data = {
            "batch_id": batch_id,
            "batch_index": batch_index,
            "total_batches": total_batches,
            "status": "COMMITTED",
            "completed_at": now_iso,
            "document_count": len(doc_records),
            "documents": doc_records,
            "metrics": metrics or {},
        }

        # 1. Atomic write for this batch checkpoint
        self._atomic_write_json(cp_path, batch_checkpoint_data)

        # 2. Update master manifest
        manifest = self.load_manifest()
        manifest["batches"][batch_id] = {
            "checkpoint_file": cp_path.name,
            "status": "COMMITTED",
            "completed_at": now_iso,
            "document_count": len(doc_records),
        }

        committed_set = set(manifest.get("global_committed_doc_ids", []))
        committed_set.update(new_doc_ids)
        manifest["global_committed_doc_ids"] = sorted(list(committed_set))
        manifest["total_batches"] = total_batches
        manifest["completed_batches"] = sum(1 for b in manifest["batches"].values() if b.get("status") == "COMMITTED")

        self.save_manifest()
        logger.info(
            "BatchCheckpointManager: Successfully committed Batch %d/%d (%d docs) -> %s",
            batch_index, total_batches, len(doc_records), cp_path.name
        )

    def reset_checkpoints(self) -> None:
        """Cleans all batch checkpoints and resets manifest (used for clean fresh runs)."""
        manifest = self.load_manifest()
        for b_info in manifest.get("batches", {}).values():
            cp_name = b_info.get("checkpoint_file")
            if cp_name:
                cp_file = self.checkpoint_dir / cp_name
                if cp_file.exists():
                    try:
                        cp_file.unlink()
                    except Exception:
                        pass
        if self.manifest_file.exists():
            try:
                self.manifest_file.unlink()
            except Exception:
                pass
        self._manifest_cache = None
        logger.info("BatchCheckpointManager: Checkpoints reset.")
