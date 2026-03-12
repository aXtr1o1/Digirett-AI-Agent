### This code is the main Lovdata ingestion pipeline that processes XML files, chunks them, generates embeddings, and stores them in Milvus and Supabase. It includes CPU-aware throttling to manage resource usage during processing.
# import warnings

# warnings.filterwarnings(
#     "ignore",
#     message="pkg_resources is deprecated as an API",
#     category=UserWarning,
# )

# import gc
# import os
# import time
# import logging

# import psutil

# from ingestion.src.processors.chunker import NorwegianLovdataChunker, TokenCounter
# from ingestion.src.processors.embedder import TokenAwareAzureEmbedder
# from ingestion.collectors.lovdata_collector import fetch_lovdata_files
# from ingestion.src.processors.text_processor import process_xml_to_text
# from ingestion.src.storage.supabase_store import SupabaseStore
# from ingestion.src.storage.milvus_store import MilvusTextStore
# from ingestion.src.config import (
#     MAX_TOKENS_PER_CHUNK,
#     OVERLAP_TOKENS,
#     LOG_FILE,
#     XML_PROCESS_WORKERS,
#     PIPELINE_CPU_WARN,
#     PIPELINE_CPU_PAUSE,
#     PIPELINE_CPU_MAX,
#     PIPELINE_DOC_SLEEP,
# )

# # -------------------------------------------------
# # Logging
# # -------------------------------------------------
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s | %(levelname)s | %(message)s",
#     handlers=[
#         logging.FileHandler(LOG_FILE, encoding="utf-8"),
#         logging.StreamHandler(),
#     ],
#     force=True,
# )
# logger = logging.getLogger("lovdata-ingestion")


# # -------------------------------------------------
# # CPU guard helpers  (all thresholds come from config — no literals)
# # -------------------------------------------------

# def _cpu_guard(label: str = "") -> None:
#     """Instant (non-blocking) CPU snapshot; sleeps if config thresholds exceeded."""
#     cpu = psutil.cpu_percent(interval=None)
#     if cpu >= PIPELINE_CPU_MAX:
#         logger.warning(f"🔴 CPU={cpu}% [{label}] — pausing 8s")
#         time.sleep(8.0)
#     elif cpu >= PIPELINE_CPU_PAUSE:
#         logger.warning(f"🟠 CPU={cpu}% [{label}] — pausing 3s")
#         time.sleep(3.0)
#     elif cpu >= PIPELINE_CPU_WARN:
#         logger.info(f"🟡 CPU={cpu}% [{label}]")


# def _wait_for_cpu(label: str = "") -> None:
#     """Block until CPU drops below PIPELINE_CPU_PAUSE (60 s max)."""
#     max_wait = 60
#     waited   = 0
#     while waited < max_wait:
#         cpu = psutil.cpu_percent(interval=1)
#         if cpu < PIPELINE_CPU_PAUSE:
#             return
#         logger.warning(
#             f"⏳ Waiting for CPU ({cpu}%) to drop below "
#             f"{PIPELINE_CPU_PAUSE}% [{label}]"
#         )
#         time.sleep(3)
#         waited += 3
#     logger.warning(f"⚠️  CPU still high after {max_wait}s — proceeding anyway")


# # -------------------------------------------------
# # Pipeline
# # -------------------------------------------------

# def run_pipeline(limit: int | None = None):
#     """
#     Complete ingestion pipeline with CPU-aware throttling.

#     All tuning values (CPU thresholds, sleep durations, worker counts) are
#     imported from config.py which reads them from the .env file.
#     No numeric literals appear in this file.
#     """
#     logger.info("🚀 Lovdata ingestion started (CPU-THROTTLED)")
#     logger.info(
#         f"   CPU warn={PIPELINE_CPU_WARN}% | "
#         f"pause={PIPELINE_CPU_PAUSE}% | "
#         f"max={PIPELINE_CPU_MAX}%"
#     )
#     logger.info(f"   Inter-doc sleep : {PIPELINE_DOC_SLEEP}s")
#     logger.info(f"   XML workers     : {XML_PROCESS_WORKERS}")
#     logger.info(
#         f"   Max tokens/chunk: {MAX_TOKENS_PER_CHUNK} | "
#         f"Overlap: {OVERLAP_TOKENS}"
#     )

#     # -- Stores & processors ------------------------------------------------
#     db_store     = SupabaseStore()
#     milvus_store = MilvusTextStore()
#     chunker      = NorwegianLovdataChunker(
#         max_tokens=MAX_TOKENS_PER_CHUNK,
#         overlap_tokens=OVERLAP_TOKENS,
#     )
#     embedder = TokenAwareAzureEmbedder()

#     # -- Fetch XML files ----------------------------------------------------
#     xml_files, archive_name = fetch_lovdata_files(limit=limit)
#     if not archive_name:
#         logger.warning("⚠️ No archives fetched")
#         return {"total_files": 0, "success": 0, "skipped": 0, "failed": 0}

#     latest_zip = archive_name[-1]

#     if not xml_files:
#         logger.warning("⚠️ No XML files fetched")
#         return {"total_files": 0, "success": 0, "skipped": 0, "failed": 0}

#     logger.info(f"\n{'='*70}")
#     logger.info("📊 PIPELINE OVERVIEW")
#     logger.info(f"{'='*70}")
#     for i, archive in enumerate(archive_name, 1):
#         logger.info(f"  {i}. {archive}")
#     logger.info(f"  Total XML files: {len(xml_files)}")
#     logger.info(f"{'='*70}\n")

#     # -- XML -> text  (worker count from config) ----------------------------
#     documents = process_xml_to_text(xml_files, max_workers=XML_PROCESS_WORKERS)
#     for doc in documents:
#         doc["archive_name"] = latest_zip

#     logger.info(f"📊 Processing {len(documents)} documents")

#     # -- Stats --------------------------------------------------------------
#     success_count      = 0
#     failed_count       = 0
#     skipped_count      = 0
#     total_chunks       = 0
#     total_split_chunks = 0
#     total_tokens       = 0
#     total_inserted_chunks = 0
#     archive_stats      = {}

#     # -- Per-document loop --------------------------------------------------
#     for idx, doc in enumerate(documents, 1):

#         # Mandatory inter-document pause (from config)
#         if idx > 1:
#             time.sleep(PIPELINE_DOC_SLEEP)

#         # CPU guard before every document
#         _cpu_guard(label=f"doc {idx}/{len(documents)}")

#         gc.collect()

#         clean_name = doc["file_name"].split(".")[0]
#         xml_path   = next(p for p in xml_files if clean_name in p)

#         # -- Classify -------------------------------------------------------
#         file_hash = db_store.calculate_hash(xml_path)
#         status    = db_store.classify_file(clean_name, file_hash)

#         if status == "UNCHANGED":
#             logger.info(f"⏭️  Unchanged, skipping: {clean_name}")
#             skipped_count += 1
#             continue
 
#         if status == "UPDATED":
#             logger.info(f"♻️  Updated — removing old embeddings: {clean_name}")
#             milvus_store.delete_by_file_name(clean_name)


#         logger.info(f"\n{'='*70}")
#         logger.info(f"[{idx}/{len(documents)}] Processing {clean_name}")
#         logger.info(f"{'='*70}")

#         # -- STEP 1: Upload XML ---------------------------------------------
#         if not db_store.upload_xml_to_storage(xml_path, clean_name):
#             logger.error(f"❌ Storage upload failed: {clean_name}")
#             failed_count += 1
#             continue

#         storage_uri = doc.get("document_url") or ""

#         # -- STEP 2: Chunking -----------------------------------------------
#         # chunk_text() returns (DocumentMetadata, List[Chunk]) — unpack both
#         try:
#             _, chunks = chunker.chunk_text(
#                 doc["text"],
#                 clean_name,
#                 doc["archive_name"],
#             )
#             if not chunks:
#                 logger.warning(f"⚠️  No chunks for {clean_name}, skipping")
#                 skipped_count += 1
#                 continue

#             split_count        = sum(1 for c in chunks if c.is_split)
#             chunk_token_counts = [c.token_count for c in chunks]
#             avg_tokens         = sum(chunk_token_counts) / len(chunk_token_counts)
#             max_tok            = max(chunk_token_counts)

#             logger.info(
#                 f"  📝 {len(chunks)} chunks | "
#                 f"✂️  {split_count} split | "
#                 f"avg {avg_tokens:.0f}t | max {max_tok}t"
#             )
#             total_chunks       += len(chunks)
#             total_split_chunks += split_count
#             total_tokens       += sum(chunk_token_counts)

#         except Exception as e:
#             logger.error(f"❌ Chunking failed for {clean_name}: {e}")
#             failed_count += 1
#             continue

#         # -- STEP 3: Build chunk dicts --------------------------------------
#         chunk_dicts = [
#             {
#                 "stable_chunk_id": c.chunk_id,
#                 "chunk_id":        c.chunk_id,
#                 "file_name":       clean_name,
#                 "file_hash":       file_hash,
#                 "url":             storage_uri,
#                 "chunk_index":     c.child_index,
#                 "parent_index":    c.parent_index,
#                 "child_index":     c.child_index,
#                 "parent_type":     str(c.parent_type),
#                 "parent_title":    c.parent_title,
#                 "text":            c.text,
#                 "enriched_text":   c.enriched_text,
#                 "token_count":     c.token_count,
#                 "is_split":        c.is_split,
#                 "split_index":     c.split_index,
#             }
#             for c in chunks
#             if c.text and c.text.strip()
#         ]

#         if not chunk_dicts:
#             logger.warning(f"⚠️  No valid chunk text for {clean_name}")
#             skipped_count += 1
#             continue

#         # -- STEP 4: Embeddings --------------------------------------------
#         _cpu_guard(label="pre-embed")

#         try:
#             chunk_dicts  = embedder.embed_chunks(chunk_dicts, text_field="enriched_text")
#             valid_chunks = [c for c in chunk_dicts if c.get("embedding") is not None]

#             if not valid_chunks:
#                 logger.error(f"❌ No valid embeddings for {clean_name}")
#                 failed_count += 1
#                 continue

#             if len(valid_chunks) < len(chunk_dicts):
#                 logger.warning(
#                     f"  ⚠️  {len(valid_chunks)}/{len(chunk_dicts)} embeddings succeeded"
#                 )

#             chunk_dicts = valid_chunks
#             logger.info(f"  ✅ {len(chunk_dicts)} embeddings generated")

#         except Exception as e:
#             logger.error(f"❌ Embedding failed for {clean_name}: {e}")
#             failed_count += 1
#             continue

#         process = psutil.Process(os.getpid())
#         mem_before = process.memory_info().rss / (1024 * 1024)  # MB

#         # -- STEP 5: Milvus insert -----------------------------------------
#         _wait_for_cpu(label=f"pre-milvus {clean_name}")

#         try:
#             result = milvus_store.insert_chunks(chunk_dicts)

#             mem_after = process.memory_info().rss / (1024 * 1024)  # MB
#             mem_used = mem_after - mem_before

#             if result.get("skipped"):
#                 logger.warning(f"  ⏭️  Duplicate skipped: {clean_name}")
#                 skipped_count += 1
#                 continue

#             inserted_count = result.get("inserted", 0)

#             if inserted_count > 0:
#                 total_inserted_chunks += inserted_count
#                 logger.info(f"  ✅ {inserted_count} vectors → Milvus")

#                 logger.info(
#                     f"  🧠 RAM used during Milvus insert: "
#                     f"{mem_used:.2f} MB "
#                     f"(Before: {mem_before:.2f} MB | After: {mem_after:.2f} MB)"
#                 )

#         except Exception as e:
#             logger.error(f"❌ Milvus insertion failed for {clean_name}: {e}")
#             try:
#                 db_store.delete_xml_from_storage(clean_name)
#                 logger.warning(f"🧹 Storage rollback completed: {clean_name}")
#             except Exception as rollback_err:
#                 logger.error(f"❌ Storage rollback failed: {rollback_err}")
#             failed_count += 1
#             continue

#         # -- STEP 6: Supabase metadata --------------------------------------
#         file_size = os.path.getsize(xml_path)
#         try:
#             db_store.insert_file_metadata(
#                 file_name=clean_name,
#                 file_hash=file_hash,
#                 file_size=file_size,
#                 zip_name=doc["archive_name"],
#                 url=storage_uri,
#             )
#             logger.info("  ✅ Metadata → Supabase")
#             success_count += 1

#             # 🔹 SINGLE FILE STATS
#             single_file_chunks = inserted_count  # from Milvus insert step

#             # 🔹 OVERALL RUNNING AVERAGE
#             if success_count > 0:
#                 overall_avg_chunks = total_inserted_chunks / success_count

#                 logger.info(
#                     f"  📊 File chunks: {single_file_chunks}"
#                 )

#                 logger.info(
#                     f"  📈 Overall avg chunks/doc: {overall_avg_chunks:.1f}"
#                 )

#             key = doc["archive_name"]
#             if key not in archive_stats:
#                 archive_stats[key] = {"files": 0, "chunks": 0}
#             archive_stats[key]["files"]  += 1
#             archive_stats[key]["chunks"] += len(chunk_dicts)

#         except Exception as e:
#             logger.error(f"❌ Metadata insert failed for {clean_name}: {e}")
#             try:
#                 db_store.delete_xml_from_storage(clean_name)
#                 logger.warning(
#                     f"🧹 Storage rollback after metadata failure: {clean_name}"
#                 )
#             except Exception as rollback_err:
#                 logger.error(f"❌ Storage rollback failed: {rollback_err}")
#             failed_count += 1
#             continue

#         logger.info(f"✅ [{idx}/{len(documents)}] Done: {clean_name}")

#     # -- Cleanup ------------------------------------------------------------
#     milvus_store.close()

#     # -- Final stats --------------------------------------------------------
#     logger.info("\n" + "=" * 70)
#     logger.info("🎉 PIPELINE COMPLETED")
#     logger.info("=" * 70)
#     logger.info(f"  Total files  : {len(documents)}")
#     logger.info(f"  ✅ Success   : {success_count}")
#     logger.info(f"  ⏭️  Skipped  : {skipped_count}")
#     logger.info(f"  ❌ Failed    : {failed_count}")
#     logger.info(f"  Total chunks : {total_chunks}")
#     logger.info(f"  Stored chunks: {total_inserted_chunks}")
#     if success_count > 0:
#         avg_chunks_per_doc = total_inserted_chunks / success_count
#         logger.info(f"  Avg chunks/doc stored: {avg_chunks_per_doc:.1f}")
#     if total_chunks > 0:
#         logger.info(
#             f"  Split chunks : {total_split_chunks} "
#             f"({total_split_chunks / total_chunks * 100:.1f}%)"
#         )
#         logger.info(f"  Total tokens : {total_tokens:,}")
#         logger.info(f"  Avg t/chunk  : {total_tokens / total_chunks:.0f}")
#     if archive_stats:
#         logger.info("\n📚 Per-archive breakdown:")
#         for archive, s in archive_stats.items():
#             logger.info(f"  {archive}: {s['files']} files, {s['chunks']} chunks")
#     logger.info("=" * 70)

#     return {
#         "total_files": len(documents),
#         "success":     success_count,
#         "skipped":     skipped_count,
#         "failed":      failed_count,
#     }


# # -------------------------------------------------
# # Entry point
# # -------------------------------------------------
# if __name__ == "__main__":
#     run_pipeline(limit=None)
#----------------------------------------------------------

"""
main.py — Per-domain ingestion pipeline
========================================
TL Requirements added:
  1. User is prompted in terminal to SELECT which XL sheet to process.
  2. Terminal shows clearly which sheet was selected.
  3. lovdata_collector.scrape_urls_from_xl() runs FIRST for that sheet only.
  4. run_pipeline() then processes ONLY the URLs from that one XL sheet.

Everything else (chunking, embedding, Milvus, Supabase, CPU guards,
append mode, dedup) is unchanged from the original.
"""

import warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated as an API", category=UserWarning)

import gc
import os
import sys
import time
import logging
from pathlib import Path
from typing import Optional

import psutil
from ingestion.src.config import CLEAN_TEXT_DIR
from ingestion.src.config import RAW_XML_DIR
from ingestion.src.processors.chunker import NorwegianLovdataChunker
from ingestion.src.processors.embedder import TokenAwareAzureEmbedder
from ingestion.src.processors.text_processor import process_xml_to_text
from ingestion.src.processors.xl_metadata_loader import load_xl_single_file
from ingestion.src.storage.supabase_store import SupabaseStore
from ingestion.src.storage.milvus_store import MilvusTextStore
from ingestion.src.config import (
    MAX_TOKENS_PER_CHUNK,
    OVERLAP_TOKENS,
    LOG_FILE,
    PIPELINE_CPU_WARN,
    PIPELINE_CPU_PAUSE,
    PIPELINE_CPU_MAX,
    PIPELINE_DOC_SLEEP,
    XL_DATASET_FOLDER,
    RAW_XML_DIR,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# URL helpers  (unchanged from original)
# ---------------------------------------------------------------------------

def _derive_lovdata_url(file_name: str) -> Optional[str]:
    import re
    stem = file_name.lower().replace(".xml", "").replace(".txt", "")
    type_map = {"nl": "lov", "sf": "forskrift"}
    m = re.match(r'^(nl|sf)-(\d{4})(\d{2})(\d{2})(?:-0*(\d+))?$', stem)
    if not m:
        return None
    prefix, year, month, day, num = m.groups()
    path = type_map.get(prefix, "lov")
    if num:
        return f"https://lovdata.no/{path}/{year}-{month}-{day}-{int(num)}"
    else:
        return f"https://lovdata.no/{path}/{year}-{month}-{day}"


def _url_to_stem(url: str) -> Optional[str]:
    """
    https://lovdata.no/lov/1814-05-17            → nl-18140517
    https://lovdata.no/lov/1997-06-13-44         → nl-19970613-0044
    https://lovdata.no/forskrift/2016-08-12-974  → sf-20160812-0974
    Also handles /dokument/NL/ and /dokument/SF/ long forms.
    """
    import re
    url = url.strip().rstrip("/")
    url = url.replace("/dokument/NL/lov/",       "/lov/")
    url = url.replace("/dokument/SF/forskrift/", "/forskrift/")
    m = re.search(r'/(lov|forskrift)/(\d{4})-(\d{2})-(\d{2})(?:-(\d+))?$', url)
    if not m:
        return None
    law_type, year, month, day, num = m.groups()
    prefix = "nl" if law_type == "lov" else "sf"
    if num:
        return f"{prefix}-{year}{month}{day}-{int(num):04d}"
    else:
        return f"{prefix}-{year}{month}{day}"


# ---------------------------------------------------------------------------
# CPU guards  (unchanged from original)
# ---------------------------------------------------------------------------

def _cpu_guard(label: str = "") -> None:
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
    max_wait = 60
    waited = 0
    while waited < max_wait:
        cpu = psutil.cpu_percent(interval=1)
        if cpu < PIPELINE_CPU_PAUSE:
            return
        logger.warning(f"⏳ Waiting for CPU ({cpu}%) [{label}]")
        time.sleep(3)
        waited += 3
    logger.warning(f"⚠️  CPU still high after {max_wait}s — proceeding")


# ---------------------------------------------------------------------------
# Append metadata to existing Milvus chunks  (unchanged from original)
# ---------------------------------------------------------------------------

def _append_milvus_metadata(
    milvus_store:    MilvusTextStore,
    file_hash:       str,
    new_domain:      str,
    new_subdomain:   str,
    new_source_type: str,
) -> bool:
    try:
        milvus_store._ensure_connection()
        existing = milvus_store.collection.query(
            expr=f'file_hash == "{file_hash}"',
            output_fields=[
                "chunk_id", "file_hash", "domain_name", "sub_domain_name",
                "source_type", "tags", "jurisdiction", "statute_id", "tier",
                "chunk_index", "parent_index", "child_index",
                "text", "parent_title", "law_short_name", "paragraph_number",
                "embedding",
            ],
            limit=16384,
        )

        if not existing:
            logger.info(f"  ℹ️  No existing Milvus chunks for file_hash={file_hash[:8]}... — skipping append")
            return False

        def _merge_field(existing_val: str, new_val: str) -> str:
            if not new_val:
                return existing_val
            existing_parts = [p.strip() for p in existing_val.split(",") if p.strip()]
            for part in [p.strip() for p in new_val.split(",") if p.strip()]:
                if part not in existing_parts:
                    existing_parts.append(part)
            return ", ".join(existing_parts)

        base             = existing[0]
        merged_domain    = _merge_field(base.get("domain_name",    ""), new_domain)
        merged_subdomain = _merge_field(base.get("sub_domain_name",""), new_subdomain)
        merged_source    = _merge_field(base.get("source_type",    ""), new_source_type)

        logger.info(
            f"  🔄 Milvus metadata append | "
            f"domain: {base.get('domain_name','')!r} → {merged_domain!r} | "
            f"sub: {base.get('sub_domain_name','')!r} → {merged_subdomain!r} | "
            f"type: {base.get('source_type','')!r} → {merged_source!r}"
        )

        milvus_store.collection.delete(f'file_hash == "{file_hash}"')
        milvus_store.collection.flush()

        chunk_dicts = []
        for c in existing:
            cd = dict(c)
            cd["domain_name"]     = merged_domain
            cd["sub_domain_name"] = merged_subdomain
            cd["source_type"]     = merged_source
            chunk_dicts.append(cd)

        milvus_metadata = {
            "domain_name":     merged_domain,
            "sub_domain_name": merged_subdomain,
            "source_type":     merged_source,
            "tags":            [],
            "jurisdiction":    base.get("jurisdiction", "NO"),
            "statute_id":      base.get("statute_id",   ""),
            "tier":            base.get("tier",          "primary"),
        }

        result = milvus_store.insert_chunks(chunk_dicts, milvus_metadata)
        logger.info(f"  ✅ Milvus metadata updated: {result.get('inserted', 0)} chunks re-inserted")
        return True

    except Exception as e:
        logger.error(f"  ❌ _append_milvus_metadata failed: {e}")
        return False


# ---------------------------------------------------------------------------
# TL requirement: XL sheet selection prompt
# ---------------------------------------------------------------------------

def _list_xl_files() -> list:
    """Return all .xlsx/.xlsm files found in XL_DATASET_FOLDER."""
    folder = XL_DATASET_FOLDER
    if not folder.exists():
        return []
    return sorted([
        f for f in (list(folder.glob("*.xlsx")) + list(folder.glob("*.xlsm")))
        if not f.name.startswith("~$")
    ])


def _resolve_xl_path(xl_input: str) -> Path:
    """
    Accept a number (menu shortcut), filename, or full path.
    Searches cwd first, then XL_DATASET_FOLDER.
    """
    xl_files = _list_xl_files()

    # Numeric menu shortcut
    if xl_input.isdigit() and xl_files:
        idx = int(xl_input) - 1
        if 0 <= idx < len(xl_files):
            return xl_files[idx]
        raise ValueError(f"Invalid selection. Choose 1–{len(xl_files)}.")

    p = Path(xl_input.replace("\\", "/"))
    if p.is_absolute() and p.exists():
        return p
    if p.exists():
        return p.resolve()
    folder = Path(XL_DATASET_FOLDER.replace("\\", "/"))
    for ext in ("", ".xlsx", ".xlsm"):
        candidate = folder / f"{p.stem}{ext}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Cannot find '{xl_input}' in cwd or '{XL_DATASET_FOLDER}'"
    )


def prompt_xl_sheet() -> Path:
    """
    TL requirement: prompt user in terminal to select which XL sheet to use.
    Shows available sheets, accepts a number or filename.
    """
    xl_files = _list_xl_files()

    print()
    print("=" * 65)
    print("  LOVDATA INGESTION — SELECT XL DATASET")
    print("=" * 65)

    if xl_files:
        print(f"\n  Available datasets in '{XL_DATASET_FOLDER}':\n")
        for i, f in enumerate(xl_files, 1):
            print(f"    [{i:>2}]  {f.name}")
        print()
        print("  Enter a number, filename, or full path.")
    else:
        print(f"\n  No XL files found in '{XL_DATASET_FOLDER}'.")
        print("  Enter the full path to your XL sheet.")

    print()
    while True:
        raw = input("  XL sheet : ").strip()
        if not raw:
            print("  Input cannot be empty — try again.\n")
            continue
        try:
            return _resolve_xl_path(raw)
        except (FileNotFoundError, ValueError) as exc:
            print(f"  ⚠️  {exc} — try again.\n")


# ---------------------------------------------------------------------------
# Main pipeline  (one XL sheet at a time — TL requirement)
# ---------------------------------------------------------------------------

def run_pipeline(xl_path: Path, xml_folder: str) -> None:
    """
    Run the full ingestion pipeline for ONE selected XL sheet.

    Parameters
    ----------
    xl_path    : Path to the selected XL file (chosen by the user).
    xml_folder : Directory containing scraped raw XML files.
    """
    logger.info("🚀 Lovdata ingestion started (per-domain mode)")
    logger.info(f"   XL sheet   : {xl_path.name}")
    logger.info(f"   XML folder : {xml_folder}")

    db_store     = SupabaseStore()
    milvus_store = MilvusTextStore()
    chunker      = NorwegianLovdataChunker(
        max_tokens=MAX_TOKENS_PER_CHUNK,
        overlap_tokens=OVERLAP_TOKENS,
    )
    embedder = TokenAwareAzureEmbedder()

    # Load ONLY the selected XL sheet  (TL requirement: one domain at a time)
    domain_name, xl_url_map = load_xl_single_file(xl_path)
    if not xl_url_map:
        logger.error(f"No URLs found in: {xl_path.name}")
        return

    # Build stem → Path map from the XML folder
    xml_folder_path = Path(xml_folder.replace("\\", "/"))
    if not xml_folder_path.exists():
        logger.error(f"❌ XML folder not found: {xml_folder_path.resolve()}")
        return

    xml_path_map: dict[str, Path] = {
        p.stem: p for p in sorted(xml_folder_path.glob("*.xml"))
    }
    if not xml_path_map:
        logger.error(f"❌ No .xml files found in: {xml_folder_path.resolve()}")
        return

    logger.info(f"📁 {len(xml_path_map)} XML files on disk | {len(xl_url_map)} URLs in XL sheet")

    total_new      = 0
    total_appended = 0
    total_skipped  = 0
    total_failed   = 0
    seen_stems:    set = set()
    url_total      = len(xl_url_map)

    logger.info(f"\n{'='*70}")
    logger.info(f"📂 Domain: {domain_name}  ({url_total} URLs in sheet)")
    logger.info(f"{'='*70}")

    for url_idx, (lovdata_url, xl_meta) in enumerate(xl_url_map.items(), 1):
        sub_domain_name = xl_meta.sub_domain_name
        source_type     = xl_meta.source_type

        xml_stem = _url_to_stem(lovdata_url)
        if not xml_stem:
            continue

        # Deduplicate: both URL forms resolve to the same XML file
        if xml_stem in seen_stems:
            continue
        seen_stems.add(xml_stem)

        xml_path_item = xml_path_map.get(xml_stem)
        if not xml_path_item:
            logger.debug(
                f"  ℹ️  [{url_idx}/{url_total}] No XML on disk for "
                f"{lovdata_url} (stem={xml_stem})"
            )
            continue

        file_hash      = db_store.calculate_hash(str(xml_path_item))
        already_exists = db_store.file_exists(file_hash)

        if already_exists:
            # ── APPEND MODE ──────────────────────────────────────────────
            logger.info(f"\n  🔁 APPEND | {xml_stem} | domain={domain_name!r}")
            _append_milvus_metadata(
                milvus_store, file_hash,
                new_domain=domain_name,
                new_subdomain=sub_domain_name,
                new_source_type=source_type,
            )
            db_store.append_law_documents_metadata(
                file_hash=file_hash,
                domain_name=domain_name,
                subdomain_name=sub_domain_name,
                source_type=source_type,
            )
            total_appended += 1
            continue

        # ── NEW FILE: full pipeline ───────────────────────────────────────
        logger.info(f"\n  🆕 NEW | {xml_stem} | domain={domain_name!r}")
        _cpu_guard(label=xml_stem)
        gc.collect()

        # Parse XML → text
        docs = process_xml_to_text([xml_path_item], max_workers=1)
        if not docs:
            logger.error(f"  ❌ Could not parse XML: {xml_stem}")
            total_failed += 1
            continue
        doc = docs[0]

        clean_file = CLEAN_TEXT_DIR / f"{xml_stem}.txt"
        with open(clean_file, "w", encoding="utf-8") as f:
            f.write(doc["text"])

        logger.info(f"  📝 Clean text saved → {clean_file.name}")

        # Upload to Supabase storage
        if not db_store.upload_xml_to_storage(str(xml_path_item), xml_stem):
            logger.error(f"  ❌ Storage upload failed: {xml_stem}")
            total_failed += 1
            continue

        # Chunk
        try:
            article_title        = doc.get("metadata", {}).get("fulltittel", "") or None
            doc_metadata, chunks = chunker.chunk_text(doc["text"], xml_stem, article_title)
            if not chunks:
                logger.warning(f"  ⚠️  No chunks: {xml_stem}")
                total_skipped += 1
                continue
            logger.info(f"  📝 {len(chunks)} chunks")
        except Exception as e:
            logger.error(f"  ❌ Chunking failed: {e}")
            total_failed += 1
            continue

        chunk_dicts = [c.to_dict() for c in chunks if c.text and c.text.strip()]
        for cd in chunk_dicts:
            cd["file_hash"] = file_hash

        # Embed
        _cpu_guard(label="pre-embed")
        try:
            chunk_dicts = embedder.embed_chunks(chunk_dicts, text_field="enriched_text")
            chunk_dicts = [c for c in chunk_dicts if c.get("embedding") is not None]
            if not chunk_dicts:
                logger.error(f"  ❌ No valid embeddings: {xml_stem}")
                total_failed += 1
                continue
            logger.info(f"  ✅ {len(chunk_dicts)} embeddings")
        except Exception as e:
            logger.error(f"  ❌ Embedding failed: {e}")
            total_failed += 1
            continue

        # Resolve statute_id
        statute_id = (
            doc.get("document_url")
            or doc_metadata.lovdata_url
            or _derive_lovdata_url(xml_stem)
            or ""
        )

        milvus_metadata = {
            "domain_name":     domain_name,
            "sub_domain_name": sub_domain_name,
            "source_type":     source_type,
            "tags":            [],
            "jurisdiction":    "NO",
            "statute_id":      statute_id,
            "tier":            "amendment" if doc_metadata.is_amendment else "primary",
        }

        logger.info(
            f"  📋 Milvus metadata | statute_id={statute_id} | "
            f"domain={domain_name!r} | sub_domain={sub_domain_name!r} | "
            f"source_type={source_type!r} | jurisdiction=NO | xl_match=True"
        )

        # Insert Milvus
        _wait_for_cpu(label=f"pre-milvus {xml_stem}")
        try:
            result = milvus_store.insert_chunks(chunk_dicts, milvus_metadata)
            logger.info(f"  ✅ {result.get('inserted', 0)} vectors → Milvus")
        except Exception as e:
            logger.error(f"  ❌ Milvus insert failed: {e}")
            db_store.delete_xml_from_storage(xml_stem)
            total_failed += 1
            continue

        # Insert Supabase
        file_size = os.path.getsize(str(xml_path_item))
        db_store.insert_law_documents_metadata(
            lovdata_url=statute_id,
            file_hash=file_hash,
            file_size=file_size,
            domain_name=domain_name,
            subdomain_name=sub_domain_name,
            source_type=source_type,
        )
        logger.info(f"  ✅ Supabase row created | domain={domain_name!r}")
        total_new += 1

        time.sleep(PIPELINE_DOC_SLEEP)

    milvus_store.close()

    logger.info("\n" + "=" * 70)
    logger.info("🎉 PIPELINE COMPLETED")
    logger.info(f"   XL sheet processed : {xl_path.name}")
    logger.info(f"   Domain             : {domain_name}")
    logger.info(f"   🆕 New ingested    : {total_new}")
    logger.info(f"   🔁 Appended        : {total_appended}")
    logger.info(f"   ⏭️  Skipped         : {total_skipped}")
    logger.info(f"   ❌ Failed          : {total_failed}")
    logger.info("=" * 70)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    xl_path = prompt_xl_sheet()

    
    print()
    print("─" * 65)
    print(f"  Selected  : {xl_path.name}")
    print(f"  Full path : {xl_path}")
    print("─" * 65)
    print()

    
    print("  STEP 1/2  Scraping Lovdata URLs from selected sheet ...")
    print()

    from ingestion.collectors.lovdata_collector import scrape_urls_from_xl
    try:
        saved_files = scrape_urls_from_xl(
            xl_path=str(xl_path),
            output_dir=Path(RAW_XML_DIR),
        )
        print(f"  {len(saved_files)} XML file(s) ready in '{RAW_XML_DIR}'")
    except Exception as exc:
        logger.error(f"Scraping failed: {exc}", exc_info=True)
        sys.exit(1)

    
    print()
    print("─" * 65)
    print("  STEP 2/2  Running ingestion pipeline ...")
    print("─" * 65)
    print()

    try:
        run_pipeline(xl_path=xl_path, xml_folder=RAW_XML_DIR)
    except Exception as exc:
        logger.error(f"Pipeline failed: {exc}", exc_info=True)
        sys.exit(1)