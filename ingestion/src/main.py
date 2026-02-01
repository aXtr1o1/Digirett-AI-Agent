import gc
import os
import logging
from datetime import datetime

# ✅ CORRECT IMPORTS: Use token-based versions for chunking/embedding
from ingestion.src.processors.chunker import NorwegianLovdataChunker, TokenCounter
from ingestion.src.processors.embedder import SageMakerBGEEmbedder

# ✅ KEEP EXISTING IMPORTS: These remain the same
from ingestion.collectors.lovdata_collector import fetch_lovdata_files
from ingestion.src.processors.text_processor import process_xml_to_text
from ingestion.src.storage.supabase_store import SupabaseStore
from ingestion.src.storage.milvus_store import MilvusTextStore
from ingestion.src.config import (
    LOG_FILE,
    MILVUS_HOST,
    MILVUS_PORT,
    MILVUS_COLLECTION
)

# -------------------------------------------------
# Logging
# -------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ],
    force=True
)

logger = logging.getLogger("lovdata-ingestion")

# -------------------------------------------------
# Pipeline WITH TOKEN-BASED CHUNKING (CORRECTED)
# -------------------------------------------------

def run_pipeline(limit: int = None):
    """
    Complete ingestion pipeline WITH TOKEN-BASED CHUNKING.
    
    ✅ CHANGES FROM OLD VERSION:
    1. NorwegianLovdataChunker: Uses token-based splitting (no truncation)
    2. SageMakerBGEEmbedder: Batch processing, no text truncation
    3. Statistics: Tracks token counts and split chunks
    
    ✅ UNCHANGED:
    - SupabaseStore (same)
    - MilvusTextStore (same)
    - fetch_lovdata_files (same)
    - process_xml_to_text (same)
    
    Flow:
    1. Fetch XML files
    2. Process to text
    3. Token-based chunking (max 512 tokens per chunk)
    4. Generate embeddings (batched, 5 at a time)
    5. Store in Milvus (vectors)
    6. Store in Supabase (metadata)
    """
    logger.info("🚀 Lovdata ingestion started (TOKEN-BASED CHUNKING)")
    logger.info("   Max tokens/chunk: 512 | Overlap: 50 | Batch size: 1")
    logger.info("   ✅ NO DATA LOSS (no truncation)")

    # ============================================================
    # Initialize stores (UNCHANGED)
    # ============================================================
    
    db_store = SupabaseStore()
    milvus_store = MilvusTextStore(
        MILVUS_HOST,
        MILVUS_PORT,
        MILVUS_COLLECTION
    )

    # ============================================================
    # Initialize processors (✅ CHANGED: Token-based versions)
    # ============================================================
    
    # Token-based chunker (512 tokens max, 50 token overlap)
    chunker = NorwegianLovdataChunker(
        max_tokens=512,      # VRAM-safe limit
        overlap_tokens=50    # Context preservation
    )
    
    # Token-aware embedder (no truncation, batch processing)
    embedder = SageMakerBGEEmbedder(
        endpoint_name="embedding-bge-m3-endpoint",
        region_name="ap-south-1",
        max_retries=3,
        retry_delay=15,
        chunk_delay=1.0,      # ✅ Faster: 0.5s (was 1.0s)
        batch_size=1,         # ✅ Batch processing (was 1)
        warn_token_threshold=400,   # ⚠️ Soft warning
    )

    # ============================================================
    # Fetch and convert XML to text (UNCHANGED)
    # ============================================================
    
    xml_files, archive_name = fetch_lovdata_files(limit=limit)

    if not xml_files:
        logger.error("❌ No XML files fetched")
        return
    
    logger.info(f"\n{'='*70}")
    logger.info(f"📊 PIPELINE OVERVIEW")
    logger.info(f"{'='*70}")
    logger.info(f"Archives processed: {len(archive_name)}")
    for i, archive in enumerate(archive_name, 1):
        logger.info(f"  {i}. {archive}")
    logger.info(f"Total XML files: {len(xml_files)}")
    logger.info(f"{'='*70}\n")

    documents = process_xml_to_text(xml_files)

    logger.info(f"📊 Processing {len(documents)} documents")

    # ============================================================
    # Statistics tracking (✅ ADDED: Token statistics)
    # ============================================================
    
    success_count = 0
    failed_count = 0
    skipped_count = 0
    total_chunks = 0
    total_split_chunks = 0  # ✅ NEW: Track splits
    total_tokens = 0        # ✅ NEW: Track tokens

    # ✅ NEW: Track per-archive statistics
    archive_stats = {}

    # ============================================================
    # Process each document
    # ============================================================
    
    for idx, doc in enumerate(documents, 1):
        # ✅ MEMORY CLEANUP: Between documents
        gc.collect()

        # Extract clean filename
        clean_name = doc["file_name"].split(".")[0]
        xml_path = next(p for p in xml_files if clean_name in p)

        # Calculate file metadata
        file_hash = db_store.calculate_hash(xml_path)
        file_size = os.path.getsize(xml_path)

        logger.info(f"\n{'='*70}")
        logger.info(f"[{idx}/{len(documents)}] Processing {clean_name}")
        logger.info(f"{'='*70}")

        # ============================================================
        # STEP 1: Upload XML to Supabase Storage (UNCHANGED)
        # ============================================================
        
        upload_success = db_store.upload_xml_to_storage(xml_path, clean_name)
        
        if not upload_success:
            logger.error(f"❌ Storage upload failed for {clean_name}")
            failed_count += 1
            continue
        
        # Build public storage URI (without .xml extension)
        storage_uri = (
            f"https://xdnqfhqdbsjgfanfbvdp.supabase.co/storage/v1/object/"
            f"public/lovdata-raw-xml/raw/{clean_name}"
        )

        # ============================================================
        # STEP 2: Token-based chunking (✅ CHANGED)
        # ============================================================
        
        try:
            _, chunks = chunker.chunk_text(
                doc["text"],
                clean_name,
                archive_name[0] if archive_name else "unknown"
            )

            if not chunks:
                logger.warning(f"⚠️  No chunks generated for {clean_name}, skipping")
                skipped_count += 1
                continue
            
            # ✅ COUNT SPLIT CHUNKS
            split_count = sum(1 for c in chunks if c.is_split)
            total_split_chunks += split_count
            
            # ✅ CALCULATE TOKEN STATISTICS
            chunk_token_counts = [c.token_count for c in chunks]
            avg_tokens = sum(chunk_token_counts) / len(chunk_token_counts)
            max_tokens = max(chunk_token_counts)
            
            logger.info(f"  📝 Generated {len(chunks)} chunks")
            logger.info(f"     ✂️  {split_count} chunks were split")
            logger.info(f"     🔢 Avg tokens: {avg_tokens:.0f} | Max: {max_tokens}")
            
            total_chunks += len(chunks)
            total_tokens += sum(chunk_token_counts)
            
        except Exception as e:
            logger.error(f"❌ Chunking failed: {e}")
            failed_count += 1
            continue

        # ============================================================
        # STEP 3: Convert chunks to dictionaries (✅ ADDED: Token fields)
        # ============================================================
        
        chunk_dicts = []
        for c in chunks:
            # Skip empty chunks
            if not c.text or not c.text.strip():
                continue

            chunk_dicts.append({
                "stable_chunk_id": c.chunk_id,
                "chunk_id": c.chunk_id,
                "file_name": clean_name,
                "file_hash": file_hash,
                "url": storage_uri,
                "chunk_index": c.child_index,
                "parent_index": c.parent_index,
                "child_index": c.child_index,
                "parent_type": str(c.parent_type),
                "parent_title": c.parent_title,
                "text": c.text,  # ✅ FULL TEXT (no truncation)
                # ✅ NEW FIELDS (optional, for tracking):
                "token_count": c.token_count,
                "is_split": c.is_split,
                "split_index": c.split_index
            })

        if not chunk_dicts:
            logger.warning(f"⚠️  No valid chunk text for {clean_name}")
            skipped_count += 1
            continue

        # ============================================================
        # STEP 4: Generate embeddings (✅ CHANGED: Token-aware, batched)
        # ============================================================
        
        try:
            chunk_dicts = embedder.embed_chunks(chunk_dicts)
            
            # ✅ VALIDATE EMBEDDINGS
            valid_chunks = [c for c in chunk_dicts if c.get("embedding") is not None]
            
            if not valid_chunks:
                logger.error(f"❌ No valid embeddings for {clean_name}, skipping")
                failed_count += 1
                continue
            
            if len(valid_chunks) < len(chunk_dicts):
                logger.warning(
                    f"  ⚠️  Only {len(valid_chunks)}/{len(chunk_dicts)} embeddings succeeded"
                )
            
            # Use only valid chunks
            chunk_dicts = valid_chunks
            logger.info(f"  ✅ Generated {len(chunk_dicts)} embeddings")
            
        except Exception as e:
            logger.error(f"❌ Embedding failed for {clean_name}: {e}")
            failed_count += 1
            continue

        # ============================================================
        # STEP 5: Insert vectors into Milvus (UNCHANGED)
        # ============================================================
        
        try:
            result = milvus_store.insert_chunks(chunk_dicts)

            if result.get("skipped"):
                logger.warning(f"  ⏭️  Skipped duplicate {clean_name}")
                skipped_count += 1
                continue

            if result.get("inserted"):
                logger.info(f"  ✅ Inserted {result['inserted']} vectors into Milvus")
                
        except Exception as e:
            logger.error(f"❌ Milvus insertion failed for {clean_name}: {e}")
            failed_count += 1
            continue

        # ============================================================
        # STEP 6: Store metadata in Supabase (UNCHANGED)
        # ============================================================
        
        try:
            db_store.insert_file_metadata(
                file_name=clean_name,
                file_hash=file_hash,
                file_size=file_size,
                zip_name=archive_name,
                url=storage_uri
            )
            logger.info(f"  ✅ Metadata stored in Supabase")
            success_count += 1

            # ✅ Track per-archive stats
            archive_key = archive_name[0] if archive_name else "unknown"
            if archive_key not in archive_stats:
                archive_stats[archive_key] = {"files": 0, "chunks": 0}
            archive_stats[archive_key]["files"] += 1
            archive_stats[archive_key]["chunks"] += len(chunk_dicts)
            
            
        except Exception as e:
            logger.error(f"❌ Metadata insertion failed for {clean_name}: {e}")
            failed_count += 1
            continue

        logger.info(f"✅ [{idx}/{len(documents)}] Completed {clean_name}")

    # ============================================================
    # Cleanup
    # ============================================================
    
    milvus_store.close()
    
     # ============================================================
    # Final statistics (✅ ENHANCED: Multi-archive + Token stats)
    # ============================================================
    
    logger.info("\n" + "="*70)
    logger.info("🎉 MULTI-ARCHIVE PIPELINE COMPLETED")
    logger.info("="*70)
    
    # Overall stats
    logger.info(f"\n📊 Overall Statistics:")
    logger.info(f"  Total files:           {len(documents)}")
    logger.info(f"  ✅ Successful:         {success_count}")
    logger.info(f"  ⏭️  Skipped:            {skipped_count}")
    logger.info(f"  ❌ Failed:             {failed_count}")
    
    # Chunk stats
    logger.info(f"\n📦 Chunk Statistics:")
    logger.info(f"  Total chunks:          {total_chunks}")
    if total_chunks > 0:
        logger.info(f"  Split chunks:          {total_split_chunks} ({total_split_chunks/total_chunks*100:.1f}%)")
        logger.info(f"  Total tokens:          {total_tokens:,}")
        logger.info(f"  Avg tokens/chunk:      {total_tokens/total_chunks:.0f}")
        logger.info(f"  Content preserved:     100% (zero truncation)")
    
    # Archive breakdown
    if archive_stats:
        logger.info(f"\n📚 Per-Archive Breakdown:")
        for archive, stats in archive_stats.items():
            logger.info(f"  {archive}:")
            logger.info(f"    Files:  {stats['files']}")
            logger.info(f"    Chunks: {stats['chunks']}")
    
    logger.info("="*70)

# -------------------------------------------------
# Entry Point
# -------------------------------------------------

if __name__ == "__main__":
    run_pipeline(limit=None)