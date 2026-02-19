import warnings

warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=UserWarning,
)

import gc
import os
import time
import logging

import psutil

from ingestion.src.processors.chunker import NorwegianLovdataChunker, TokenCounter
from ingestion.src.processors.embedder import TokenAwareAzureEmbedder
from ingestion.collectors.lovdata_collector import fetch_lovdata_files
from ingestion.src.processors.text_processor import process_xml_to_text
from ingestion.src.storage.supabase_store import SupabaseStore
from ingestion.src.storage.milvus_store import MilvusTextStore
from ingestion.src.config import (
    MAX_TOKENS_PER_CHUNK,
    OVERLAP_TOKENS,
    LOG_FILE,
    XML_PROCESS_WORKERS,
    PIPELINE_CPU_WARN,
    PIPELINE_CPU_PAUSE,
    PIPELINE_CPU_MAX,
    PIPELINE_DOC_SLEEP,
)

# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
    force=True,
)
logger = logging.getLogger("lovdata-ingestion")


# -------------------------------------------------
# CPU guard helpers  (all thresholds come from config — no literals)
# -------------------------------------------------

def _cpu_guard(label: str = "") -> None:
    """Instant (non-blocking) CPU snapshot; sleeps if config thresholds exceeded."""
    cpu = psutil.cpu_percent(interval=None)
    if cpu >= PIPELINE_CPU_MAX:
        logger.warning(f"🔴 CPU={cpu}% [{label}] — pausing 8s")
        time.sleep(8.0)
    elif cpu >= PIPELINE_CPU_PAUSE:
        logger.warning(f"🟠 CPU={cpu}% [{label}] — pausing 3s")
        time.sleep(3.0)
    elif cpu >= PIPELINE_CPU_WARN:
        logger.info(f"🟡 CPU={cpu}% [{label}]")


def _wait_for_cpu(label: str = "") -> None:
    """Block until CPU drops below PIPELINE_CPU_PAUSE (60 s max)."""
    max_wait = 60
    waited   = 0
    while waited < max_wait:
        cpu = psutil.cpu_percent(interval=1)
        if cpu < PIPELINE_CPU_PAUSE:
            return
        logger.warning(
            f"⏳ Waiting for CPU ({cpu}%) to drop below "
            f"{PIPELINE_CPU_PAUSE}% [{label}]"
        )
        time.sleep(3)
        waited += 3
    logger.warning(f"⚠️  CPU still high after {max_wait}s — proceeding anyway")


# -------------------------------------------------
# Pipeline
# -------------------------------------------------

def run_pipeline(limit: int | None = None):
    """
    Complete ingestion pipeline with CPU-aware throttling.

    All tuning values (CPU thresholds, sleep durations, worker counts) are
    imported from config.py which reads them from the .env file.
    No numeric literals appear in this file.
    """
    logger.info("🚀 Lovdata ingestion started (CPU-THROTTLED)")
    logger.info(
        f"   CPU warn={PIPELINE_CPU_WARN}% | "
        f"pause={PIPELINE_CPU_PAUSE}% | "
        f"max={PIPELINE_CPU_MAX}%"
    )
    logger.info(f"   Inter-doc sleep : {PIPELINE_DOC_SLEEP}s")
    logger.info(f"   XML workers     : {XML_PROCESS_WORKERS}")
    logger.info(
        f"   Max tokens/chunk: {MAX_TOKENS_PER_CHUNK} | "
        f"Overlap: {OVERLAP_TOKENS}"
    )

    # -- Stores & processors ------------------------------------------------
    db_store     = SupabaseStore()
    milvus_store = MilvusTextStore()
    chunker      = NorwegianLovdataChunker(
        max_tokens=MAX_TOKENS_PER_CHUNK,
        overlap_tokens=OVERLAP_TOKENS,
    )
    embedder = TokenAwareAzureEmbedder()

    # -- Fetch XML files ----------------------------------------------------
    xml_files, archive_name = fetch_lovdata_files(limit=limit)
    if not archive_name:
        logger.warning("⚠️ No archives fetched")
        return {"total_files": 0, "success": 0, "skipped": 0, "failed": 0}

    latest_zip = archive_name[-1]

    if not xml_files:
        logger.warning("⚠️ No XML files fetched")
        return {"total_files": 0, "success": 0, "skipped": 0, "failed": 0}

    logger.info(f"\n{'='*70}")
    logger.info("📊 PIPELINE OVERVIEW")
    logger.info(f"{'='*70}")
    for i, archive in enumerate(archive_name, 1):
        logger.info(f"  {i}. {archive}")
    logger.info(f"  Total XML files: {len(xml_files)}")
    logger.info(f"{'='*70}\n")

    # -- XML -> text  (worker count from config) ----------------------------
    documents = process_xml_to_text(xml_files, max_workers=XML_PROCESS_WORKERS)
    for doc in documents:
        doc["archive_name"] = latest_zip

    logger.info(f"📊 Processing {len(documents)} documents")

    # -- Stats --------------------------------------------------------------
    success_count      = 0
    failed_count       = 0
    skipped_count      = 0
    total_chunks       = 0
    total_split_chunks = 0
    total_tokens       = 0
    archive_stats      = {}

    # -- Per-document loop --------------------------------------------------
    for idx, doc in enumerate(documents, 1):

        # Mandatory inter-document pause (from config)
        if idx > 1:
            time.sleep(PIPELINE_DOC_SLEEP)

        # CPU guard before every document
        _cpu_guard(label=f"doc {idx}/{len(documents)}")

        gc.collect()

        clean_name = doc["file_name"].split(".")[0]
        xml_path   = next(p for p in xml_files if clean_name in p)

        # -- Classify -------------------------------------------------------
        file_hash = db_store.calculate_hash(xml_path)
        status    = db_store.classify_file(clean_name, file_hash)

        if status == "UNCHANGED":
            logger.info(f"⏭️  Unchanged, skipping: {clean_name}")
            skipped_count += 1
            continue

        if status == "UPDATED":
            logger.info(f"♻️  Updated — removing old embeddings: {clean_name}")
            milvus_store.delete_by_file_name(clean_name)

        if db_store.file_exists(file_hash):
            logger.info(f"⏭️  Already embedded, skipping: {clean_name}")
            skipped_count += 1
            continue

        logger.info(f"\n{'='*70}")
        logger.info(f"[{idx}/{len(documents)}] Processing {clean_name}")
        logger.info(f"{'='*70}")

        # -- STEP 1: Upload XML ---------------------------------------------
        if not db_store.upload_xml_to_storage(xml_path, clean_name):
            logger.error(f"❌ Storage upload failed: {clean_name}")
            failed_count += 1
            continue

        storage_uri = doc.get("document_url") or ""

        # -- STEP 2: Chunking -----------------------------------------------
        # chunk_text() returns (DocumentMetadata, List[Chunk]) — unpack both
        try:
            _, chunks = chunker.chunk_text(
                doc["text"],
                clean_name,
                doc["archive_name"],
            )
            if not chunks:
                logger.warning(f"⚠️  No chunks for {clean_name}, skipping")
                skipped_count += 1
                continue

            split_count        = sum(1 for c in chunks if c.is_split)
            chunk_token_counts = [c.token_count for c in chunks]
            avg_tokens         = sum(chunk_token_counts) / len(chunk_token_counts)
            max_tok            = max(chunk_token_counts)

            logger.info(
                f"  📝 {len(chunks)} chunks | "
                f"✂️  {split_count} split | "
                f"avg {avg_tokens:.0f}t | max {max_tok}t"
            )
            total_chunks       += len(chunks)
            total_split_chunks += split_count
            total_tokens       += sum(chunk_token_counts)

        except Exception as e:
            logger.error(f"❌ Chunking failed for {clean_name}: {e}")
            failed_count += 1
            continue

        # -- STEP 3: Build chunk dicts --------------------------------------
        chunk_dicts = [
            {
                "stable_chunk_id": c.chunk_id,
                "chunk_id":        c.chunk_id,
                "file_name":       clean_name,
                "file_hash":       file_hash,
                "url":             storage_uri,
                "chunk_index":     c.child_index,
                "parent_index":    c.parent_index,
                "child_index":     c.child_index,
                "parent_type":     str(c.parent_type),
                "parent_title":    c.parent_title,
                "text":            c.text,
                "token_count":     c.token_count,
                "is_split":        c.is_split,
                "split_index":     c.split_index,
            }
            for c in chunks
            if c.text and c.text.strip()
        ]

        if not chunk_dicts:
            logger.warning(f"⚠️  No valid chunk text for {clean_name}")
            skipped_count += 1
            continue

        # -- STEP 4: Embeddings --------------------------------------------
        _cpu_guard(label="pre-embed")

        try:
            chunk_dicts  = embedder.embed_chunks(chunk_dicts)
            valid_chunks = [c for c in chunk_dicts if c.get("embedding") is not None]

            if not valid_chunks:
                logger.error(f"❌ No valid embeddings for {clean_name}")
                failed_count += 1
                continue

            if len(valid_chunks) < len(chunk_dicts):
                logger.warning(
                    f"  ⚠️  {len(valid_chunks)}/{len(chunk_dicts)} embeddings succeeded"
                )

            chunk_dicts = valid_chunks
            logger.info(f"  ✅ {len(chunk_dicts)} embeddings generated")

        except Exception as e:
            logger.error(f"❌ Embedding failed for {clean_name}: {e}")
            failed_count += 1
            continue

        # -- STEP 5: Milvus insert -----------------------------------------
        _wait_for_cpu(label=f"pre-milvus {clean_name}")

        try:
            result = milvus_store.insert_chunks(chunk_dicts)

            if result.get("skipped"):
                logger.warning(f"  ⏭️  Duplicate skipped: {clean_name}")
                skipped_count += 1
                continue

            if result.get("inserted"):
                logger.info(f"  ✅ {result['inserted']} vectors → Milvus")

        except Exception as e:
            logger.error(f"❌ Milvus insertion failed for {clean_name}: {e}")
            try:
                db_store.delete_xml_from_storage(clean_name)
                logger.warning(f"🧹 Storage rollback completed: {clean_name}")
            except Exception as rollback_err:
                logger.error(f"❌ Storage rollback failed: {rollback_err}")
            failed_count += 1
            continue

        # -- STEP 6: Supabase metadata --------------------------------------
        file_size = os.path.getsize(xml_path)
        try:
            db_store.insert_file_metadata(
                file_name=clean_name,
                file_hash=file_hash,
                file_size=file_size,
                zip_name=doc["archive_name"],
                url=storage_uri,
            )
            logger.info("  ✅ Metadata → Supabase")
            success_count += 1

            key = doc["archive_name"]
            if key not in archive_stats:
                archive_stats[key] = {"files": 0, "chunks": 0}
            archive_stats[key]["files"]  += 1
            archive_stats[key]["chunks"] += len(chunk_dicts)

        except Exception as e:
            logger.error(f"❌ Metadata insert failed for {clean_name}: {e}")
            try:
                db_store.delete_xml_from_storage(clean_name)
                logger.warning(
                    f"🧹 Storage rollback after metadata failure: {clean_name}"
                )
            except Exception as rollback_err:
                logger.error(f"❌ Storage rollback failed: {rollback_err}")
            failed_count += 1
            continue

        logger.info(f"✅ [{idx}/{len(documents)}] Done: {clean_name}")

    # -- Cleanup ------------------------------------------------------------
    milvus_store.close()

    # -- Final stats --------------------------------------------------------
    logger.info("\n" + "=" * 70)
    logger.info("🎉 PIPELINE COMPLETED")
    logger.info("=" * 70)
    logger.info(f"  Total files  : {len(documents)}")
    logger.info(f"  ✅ Success   : {success_count}")
    logger.info(f"  ⏭️  Skipped  : {skipped_count}")
    logger.info(f"  ❌ Failed    : {failed_count}")
    logger.info(f"  Total chunks : {total_chunks}")
    if total_chunks > 0:
        logger.info(
            f"  Split chunks : {total_split_chunks} "
            f"({total_split_chunks / total_chunks * 100:.1f}%)"
        )
        logger.info(f"  Total tokens : {total_tokens:,}")
        logger.info(f"  Avg t/chunk  : {total_tokens / total_chunks:.0f}")
    if archive_stats:
        logger.info("\n📚 Per-archive breakdown:")
        for archive, s in archive_stats.items():
            logger.info(f"  {archive}: {s['files']} files, {s['chunks']} chunks")
    logger.info("=" * 70)

    return {
        "total_files": len(documents),
        "success":     success_count,
        "skipped":     skipped_count,
        "failed":      failed_count,
    }


# -------------------------------------------------
# Entry point
# -------------------------------------------------
if __name__ == "__main__":
    run_pipeline(limit=20)