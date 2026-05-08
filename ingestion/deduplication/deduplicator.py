from __future__ import annotations

import logging
import os
from typing import Optional, Set

from supabase import create_client, Client

logger = logging.getLogger(__name__)


class Deduplicator:
    def __init__(self, table_name: Optional[str] = None) -> None:
        self.table_name: str = (
            table_name
            or os.environ.get("SUPABASE_XAPI_TABLE", "")
            or "demo_1"
        )
        self.seen_doc_ids: Set[str] = set()
        self.supabase: Optional[Client] = None

        supabase_url = os.environ.get("SUPABASE_URL", "").strip()
        supabase_key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

        if supabase_url and supabase_key:
            try:
                self.supabase = create_client(supabase_url, supabase_key)
                logger.info(
                    "Deduplicator: Supabase client ready | table=%s", self.table_name
                )
            except Exception as exc:
                logger.error(
                    "Deduplicator: Failed to init Supabase client: %s", exc
                )
        else:
            logger.warning(
                "Deduplicator: SUPABASE_URL or SUPABASE_SERVICE_KEY not set "
                "— persistent dedup disabled, in-memory only."
            )

    def check(self, doc: dict) -> dict:
        doc_id: str = doc.get("doc_id") or doc.get("dok_id") or ""
        if not doc_id:
            logger.warning("Deduplicator: doc has no doc_id/dok_id — skipping dedup check.")
            doc["is_duplicate"] = False
            return doc

        # 1. In-memory check (same run)
        if doc_id in self.seen_doc_ids:
            doc["is_duplicate"] = True
            logger.debug("Duplicate (in-memory): %s", doc_id)
            return doc

        # 2. Supabase persistent check
        if self.supabase:
            try:
                res = (
                    self.supabase.table(self.table_name)
                    .select("dok_id")
                    .eq("dok_id", doc_id)
                    .eq("fetch_status", "completed")
                    .limit(1)
                    .execute()
                )
                if res.data:
                    doc["is_duplicate"] = True
                    logger.debug("Duplicate (Supabase): %s", doc_id)
                    return doc
            except Exception as exc:
                logger.warning(
                    "Deduplicator: Supabase lookup failed for %s: %s — treating as new.",
                    doc_id,
                    exc,
                )

        # Not a duplicate
        self.seen_doc_ids.add(doc_id)
        doc["is_duplicate"] = False
        return doc

    def mark_seen(self, doc_id: str) -> None:
        """
        Manually register a doc_id as seen (e.g. after a successful upsert).
        """
        self.seen_doc_ids.add(doc_id)