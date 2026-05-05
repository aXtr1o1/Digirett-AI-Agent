# from __future__ import annotations

import json as _json
import logging
import os
import sys
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load .env before any other imports
load_dotenv()

# ---------------------------------------------------------------------------
# Env vars — resolved once here, passed explicitly to components
# ---------------------------------------------------------------------------

SUPABASE_XAPI_BUCKET: str = os.environ.get("SUPABASE_XAPI_BUCKET", "demo_1")
SUPABASE_XAPI_TABLE: str = os.environ.get("SUPABASE_XAPI_TABLE", "demo_1")
MILVUS_COLLECTION: str = os.environ.get("MILVUS_COLLECTION", "demo_data")

# ---------------------------------------------------------------------------
# Internal imports (after env load)
# ---------------------------------------------------------------------------

from ingestion.factory.adapter_factory import AdapterFactory
from ingestion.validation.validation_gate import PipelineValidationGate
from ingestion.deduplication.deduplicator import Deduplicator
from ingestion.collectors.xapi_collector import SupabaseXAPIStore, build_storage_path
from ingestion.src.processors.chunker import DigiRettChunker
from ingestion.src.processors.embedder import TokenAwareAzureEmbedder
from ingestion.src.storage.milvus_store import MilvusTextStore
from ingestion.src.utils.reference_logger import log_for_reference

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("digirett-pipeline")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if isinstance(value, float) and value != value:  # NaN check
            return ""
    except Exception:
        pass
    return str(value).strip()


# ---------------------------------------------------------------------------
# 6-Step Pipeline
# ---------------------------------------------------------------------------


def run_layered_pipeline(
    source_name: str = "xapi",
    dry_run: bool = False,
    input_path: Optional[str] = None,
    limit: Optional[int] = None,
    refresh: bool = False,
) -> Dict[str, int]:
    """
    Unified Ingestion Flow:

    Step 1 — Fetch (XAPIAdapter.fetch calls XAPI HTTP endpoints)
    Step 2 — Store (adapter uploads JSON to bucket + upserts metadata row)
              NOTE: Steps 1+2 are fused inside the adapter because fetching
              detail+paragraphs is expensive; we don't want to do it twice.
              The adapter returns lightweight refs; main.py drives Steps 3-7.
    Step 3 — Normalise (download bucket JSON → plain text via content_text)
    Step 4 — Deduplicate (dok_id check in Supabase; upsert if exists)
    Step 5 — Validate (field + business rules; skip FAIL docs, log errors)
    Step 6 — Chunk & Embed
    Step 7 — Milvus store
    """
    logger.info("=" * 88)
    logger.info("DIGIRETT PIPELINE STARTED")
    logger.info(
        "source=%s | bucket=%s | table=%s | collection=%s",
        source_name,
        SUPABASE_XAPI_BUCKET,
        SUPABASE_XAPI_TABLE,
        MILVUS_COLLECTION,
    )
    logger.info("=" * 88)

    stats: Dict[str, int] = {
        "docs_fetched": 0,
        "docs_stored": 0,
        "docs_normalised": 0,
        "docs_duplicates": 0,
        "docs_validated": 0,
        "docs_processed": 0,
        "docs_failed": 0,
    }

    # ── STEP 1 + 2: FETCH & STORE ──────────────────────────────────────────
    logger.info("\n[STEP 1+2] FETCHING AND STORING DATA...")

    factory = AdapterFactory()
    adapter = factory.create(source_name)

    if limit:
        adapter.config["fetch_limit"] = limit
    if refresh:
        adapter.config["refresh"] = True

    # adapter.fetch() performs Steps 1+2 and returns lightweight ref dicts.
    # Each ref dict: { dok_id, domain_name, source_id, already_stored }
    refs: List[Dict[str, Any]] = adapter.fetch(
    input_path=input_path,
    )

    stats["docs_fetched"] = len(refs)
    stats["docs_stored"] = len(refs)  # every ref was either upserted or already stored
    logger.info("Fetched %d document references.", stats["docs_fetched"])

    # ── Per-document components (instantiated once, reused) ────────────────
    # FIX: Deduplicator receives table_name explicitly — no XAPI-specific import
    store = SupabaseXAPIStore()
    gate = PipelineValidationGate()
    deduplicator = Deduplicator(table_name=SUPABASE_XAPI_TABLE)
    chunker = DigiRettChunker()
    embedder = TokenAwareAzureEmbedder()
    milvus_store = MilvusTextStore()


    # ── MAIN LOOP (STEPS 3-7) ──────────────────────────────────────────────
    for idx, ref in enumerate(refs, 1):
        # Support both the fixed adapter shape {"dok_id": ..., "domain_name": ...}
        # and the original adapter shape {"metadata": {"dok_id": ...}, "domain_name": ...}
        dok_id: str = (
            ref.get("dok_id")
            or ref.get("doc_id")
            or ref.get("source_id")
            or (ref.get("metadata") or {}).get("dok_id")
            or ""
        )
        if not dok_id:
            logger.warning("[%d/%d] Ref missing dok_id — skipping.", idx, len(refs))
            continue

        domain_name: str = ref.get("domain_name") or "unknown"
        logger.info("\n[%d/%d] PROCESSING: %s", idx, len(refs), dok_id)

        try:
            # ── STEP 3: NORMALISE ─────────────────────────────────────────
            logger.info("  Step 3: Normalising from bucket...")

            storage_path = build_storage_path(dok_id)
            try:
                raw_bytes = store.client.storage.from_(SUPABASE_XAPI_BUCKET).download(
                    storage_path
                )
                retrieved_json = _json.loads(raw_bytes)
            except Exception as exc:
                logger.error(
                    "  [FAIL] Bucket download failed for %s: %s", dok_id, exc
                )
                stats["docs_failed"] += 1
                continue

            # FIX: one canonical path — always `content_text` (written by map_paragraph)
            paragraphs = retrieved_json.get("paragraphs", [])
            text_content = "\n\n".join(
                p.get("content_text", "")
                for p in paragraphs
                if p.get("content_text", "").strip()
            )

            meta_block = retrieved_json.get("metadata", {})

            doc: Dict[str, Any] = {
                "doc_id": dok_id,
                # FIX: key is "source" — matches validation_rules.yaml required_fields
                "source": source_name,
                "title": _safe_str(meta_block.get("doc_title")) or "No Title",
                "content": text_content,
                "metadata": meta_block,
                "raw_data": retrieved_json,
                "source_url": _safe_str(meta_block.get("source_doc_url")),
                # FIX: version_date may be None — use empty string, not None,
                #      so field_validator doesn't blow up on str(None)
                "version_date": _safe_str(meta_block.get("effective_date")),
                "domain": domain_name,
                "subdomain": "",
            }

            stats["docs_normalised"] += 1

            # ── STEP 4: DEDUPLICATE (upsert strategy) ────────────────────
            if not refresh:
                logger.info("  Step 4: Deduplicating by dok_id...")
                doc = deduplicator.check(doc)

                if doc.get("is_duplicate"):
                    # Upsert per requirement: update existing Supabase row with
                    # latest domain/subdomain info, then continue to embed/store
                    # in Milvus anyway. (If you want pure-skip, change to:
                    #   stats["docs_duplicates"] += 1; continue)
                    logger.info(
                        "  [DUP] Already in Supabase (dok_id=%s) — will upsert metadata "
                        "and re-embed into Milvus.",
                        dok_id,
                    )
                    stats["docs_duplicates"] += 1
                    # Fall through — do NOT continue; we still run Steps 5-7
            else:
                logger.info("  Step 4: Skipping dedup (refresh mode)")

            # ── STEP 5: VALIDATE ──────────────────────────────────────────
            logger.info("  Step 5: Validating...")
            doc = gate.evaluate(doc)

            if doc.get("validation_status") == "FAIL":
                logger.warning(
                    "  [SKIP] Validation FAIL for %s: %s",
                    dok_id,
                    doc.get("validation_errors"),
                )
                stats["docs_failed"] += 1
                continue

            stats["docs_validated"] += 1
            domain_name = doc.get("domain") or domain_name
            doc["domain"] = domain_name

            # Audit log
            try:
                log_for_reference(dok_id, doc["raw_data"], doc["content"], is_xml=False)
            except Exception:
                pass  # audit log failure must not abort pipeline

            # ── STEP 6: CHUNK & EMBED ─────────────────────────────────────
            logger.info("  Step 6: Chunking & Embedding...")
            chunk_objs = chunker.chunk(
                text=doc["content"],
                source_id=dok_id,
                source_url=doc["metadata"].get("source_doc_url", ""),
                doc_title=doc["title"],
                domain=doc["domain"],
                subdomain=doc["subdomain"],
                source_type="law",
                tier=1,
                version_date=doc["metadata"].get("effective_date", ""),
            )

            if not chunk_objs:
                logger.warning("  [FAIL] No chunks generated for %s.", dok_id)
                stats["docs_failed"] += 1
                continue

            embedder.embed_chunks(chunk_objs)

            # ── STEP 7: MILVUS STORE ──────────────────────────────────────
            logger.info(
                "  Step 7: Persisting to Milvus (collection=%s)...", MILVUS_COLLECTION
            )

            chunks_by_section: Dict[str, List] = defaultdict(list)
            for c in chunk_objs:
                ref_key = c.get("section_ref") or "§1"
                chunks_by_section[ref_key].append(c)

            if not dry_run:
                for section_ref, section_chunks in chunks_by_section.items():
                    milvus_metadata = {
                        "document_id": dok_id,
                        "source_doc_url": doc["metadata"].get("source_doc_url", ""),
                        "section_ref": section_ref,
                        "domain": doc["domain"],
                        "subdomain": doc["subdomain"],
                        "b2b_b2c": "BOTH",
                        "tier": "1",
                        "jurisdiction": "NO",
                    }
                    milvus_store.insert_chunks(section_chunks, milvus_metadata)

                # Upsert Supabase metadata row with final status
                try:
                    store.client.table(SUPABASE_XAPI_TABLE).upsert(
                        {
                            "dok_id": dok_id,
                            "fetch_status": "completed",
                            "subdomain": "",
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        },
                        on_conflict="dok_id",
                    ).execute()
                except Exception as sync_exc:
                    logger.warning(
                        "  [WARN] Could not upsert status to Supabase: %s", sync_exc
                    )

            stats["docs_processed"] += 1
            logger.info(
                "  [OK] %s — %d sections → Milvus", dok_id, len(chunks_by_section)
            )

        except Exception as exc:
            logger.error(
                "  [ERROR] Fatal failure for %s: %s", dok_id, exc, exc_info=True
            )
            stats["docs_failed"] += 1

    # ── SUMMARY ───────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 88)
    logger.info("PIPELINE SUMMARY")
    logger.info("  Fetched:    %d", stats["docs_fetched"])
    logger.info("  Stored:     %d", stats["docs_stored"])
    logger.info("  Normalised: %d", stats["docs_normalised"])
    logger.info("  Duplicates: %d (upserted)", stats["docs_duplicates"])
    logger.info("  Validated:  %d", stats["docs_validated"])
    logger.info("  Processed:  %d", stats["docs_processed"])
    logger.info("  Failed:     %d", stats["docs_failed"])
    logger.info("=" * 88)

    return stats


# ---------------------------------------------------------------------------
# Legacy Excel pipeline stub
# ---------------------------------------------------------------------------


def run_pipeline(workbook_path: Path) -> None:
    logger.info("Running legacy Excel pipeline for %s...", workbook_path)
    # Stub — focus is the unified XAPI pipeline above.


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DigiRett Unified Ingestion Pipeline")
    parser.add_argument(
        "--mode",
        type=str,
        default="pipeline",
        choices=["pipeline", "xapi", "excel"],
    )
    parser.add_argument("--source", type=str, default="xapi")
    parser.add_argument("--domain", type=str, help="Specific domain key")
    parser.add_argument("--limit", type=int, help="Limit number of docs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh", action="store_true")

    args = parser.parse_args()

    if args.mode in ("pipeline", "xapi"):
        run_layered_pipeline(
            source_name=args.source,
            input_path=args.domain,
            limit=args.limit,
            dry_run=args.dry_run,
            refresh=args.refresh,
        )
    else:
        from ingestion.src.config import XL_DATASET_FOLDER
        run_pipeline(Path(XL_DATASET_FOLDER))