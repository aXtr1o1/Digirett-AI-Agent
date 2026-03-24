"""
Production Lovdata Ingestion Pipeline - 53 Files
WITHOUT Supabase - Only Milvus storage with URL field

Flow:
1. Fetch XML files from Lovdata (53 files)
2. Convert XML → clean text
3. Chunk text (SAFE: max 1800 chars per chunk)
4. Generate embeddings (SAFE: one at a time, 512 tokens)
5. Store in Milvus (vectors + metadata + URL)
"""
'''
import gc
import os
import logging
import hashlib
from datetime import datetime
from pathlib import Path

import torch

from ingestion.src.processors.chunker import NorwegianLovdataChunker
from ingestion.src.processors.embedder_sagemaker import SageMakerBGEEmbedder
from ingestion.src.processors.text_processor import process_xml_to_text
from ingestion.src.storage.milvus_store import MilvusLovdataStore
from ingestion.src.config import (
    MAX_TOKENS_PER_CHUNK,
    OVERLAP_TOKENS,
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
        logging.StreamHandler(),
    ],
    force=True,
)

logger = logging.getLogger("lovdata-production")

# -------------------------------------------------
# Local XML configuration
# -------------------------------------------------

RAW_XML_DIR = Path("data/raw_xml")
ARCHIVE_NAME = "local_raw_xml"
# -------------------------------------------------
# Helper Functions
# -------------------------------------------------

def calculate_file_hash(content: str) -> str:
    """Calculate SHA-256 hash of file content"""
    try:
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    except Exception as e:
        logger.error(f"Error hashing content: {e}")
        return hashlib.sha256(b"error").hexdigest()

# -------------------------------------------------
# Main Pipeline
# -------------------------------------------------

def run_pipeline(limit: int = 53):
    """
    Complete ingestion pipeline for 53 files.
    
    Args:
        limit: Number of files to process (default: 53)
    """
    
    start_time = datetime.now()
    
    logger.info("=" * 70)
    logger.info("🚀 LOVDATA PRODUCTION PIPELINE - 53 FILES")
    logger.info("=" * 70)
    logger.info(f"   Target: {limit} files")
    logger.info(f"   Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    
    # Statistics
    stats = {
        "total_files": 0,
        "successful": 0,
        "failed": 0,
        "total_chunks": 0,
        "skipped_duplicates": 0
    }
    
    failed_files = []
    
    try:
        # ============================================================
        # STEP 1: Initialize Components
        # ============================================================
        
        logger.info("\n📦 Initializing components...")
        
        # Milvus store (vectors + metadata)
        milvus_store = MilvusLovdataStore(
            milvus_host=MILVUS_HOST,
            milvus_port=MILVUS_PORT,
            collection_name=MILVUS_COLLECTION
        )
        logger.info("   ✅ Milvus store initialized")
        
        # Chunker with SAFE splitting
        chunker = NorwegianLovdataChunker()
        logger.info("   ✅ Chunker initialized (SAFE mode)")
        
        # Embedder with ULTRA SAFE settings
        embedder = SageMakerBGEEmbedder(
            endpoint_name="embedding-bge-m3-endpoint",
            region_name="ap-south-1",
            max_text_length=512,        # ✔ valid
            max_chunks_per_batch=1,     # ✔ valid
            chunk_delay=1.0             # ✔ valid
            )
        logger.info("   ✅ Embedder initialized (ULTRA SAFE mode)")
        
        # ============================================================
        # STEP 2: Fetch XML Files
        # ============================================================
        
        logger.info("\n📥 Loading XML files from local folder...")

        xml_files = sorted(RAW_XML_DIR.glob("*.xml"))

        if not xml_files:
            raise RuntimeError(f"No XML files found in {RAW_XML_DIR}")

        if limit:
            xml_files = xml_files[:limit]

        archive_name = ARCHIVE_NAME

        logger.info(f"   ✅ Found {len(xml_files)} XML files")

        
        # ============================================================
        # STEP 3: Convert XML to Clean Text
        # ============================================================
        
        logger.info("\n🔄 Converting XML to clean text...")
        documents = process_xml_to_text(xml_files, max_workers=4)
        logger.info(f"   ✅ Converted {len(documents)} documents")
        
        stats["total_files"] = len(documents)
        
        # ============================================================
        # STEP 4: Process Each Document
        # ============================================================
        
        logger.info("\n" + "=" * 70)
        logger.info("📊 PROCESSING DOCUMENTS")
        logger.info("=" * 70)
        
        for idx, doc in enumerate(documents, 1):
            try:
                # Memory cleanup
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                
                # Extract metadata
                file_name = doc["file_name"]
                clean_name = file_name.replace(".xml", "").replace(".txt", "")
                text = doc["text"]

                # ✅ URL COMES FROM XML METADATA
                url = doc.get("metadata", {}).get("url", "")
                
                logger.info(f"\n[{idx}/{len(documents)}] 📄 {clean_name}")
                logger.info("-" * 70)
                
                # Calculate file hash
                file_hash = calculate_file_hash(text)
                
                # ========================================================
                # Chunking (SAFE: max 1800 chars per chunk)
                # ========================================================
                
                logger.info("   ✂️  Chunking...")
                metadata, chunks = chunker.chunk_text(
                    text=text,
                    file_name=clean_name,
                    zip_name=archive_name
                )
                
                # Filter out empty chunks
                valid_chunks = [c for c in chunks if c.text and c.text.strip()]
                
                if not valid_chunks:
                    logger.warning(f"   ⚠️  No valid chunks, skipping")
                    failed_files.append((clean_name, "No valid chunks"))
                    stats["failed"] += 1
                    continue
                
                logger.info(f"   ✅ Created {len(valid_chunks)} chunks")
                
                # Verify chunk sizes
                max_chunk_size = max(len(c.text) for c in valid_chunks)
                if max_chunk_size > 2000:
                    logger.warning(f"   ⚠️  Max chunk size: {max_chunk_size} chars (might cause issues)")
                
                # ========================================================
                # Prepare Payload
                # ========================================================
                
                chunk_dicts = []
                for i, chunk in enumerate(valid_chunks):
                    chunk_dicts.append({
                        "stable_chunk_id": chunk.chunk_id,
                        "file_name": clean_name,
                        "file_hash": file_hash,
                        "chunk_index": i,
                        "parent_index": chunk.parent_index,
                        "child_index": chunk.child_index,
                        "parent_type": chunk.parent_type,
                        "parent_title": chunk.parent_title,
                        "text": chunk.text,
                        "url": url
                    })
                
                # ========================================================
                # Embedding (SAFE: one at a time, 512 tokens)
                # ========================================================
                logger.info("   🧠 Generating embeddings...")

                chunk_dicts = embedder.embed_chunks(chunk_dicts)

                valid_chunks = [c for c in chunk_dicts if c.get("embedding")]

                if not valid_chunks:
                    logger.error("   ❌ No valid embeddings returned")
                    failed_files.append((clean_name, "No embeddings"))
                    stats["failed"] += 1
                    continue

                chunk_dicts = valid_chunks
                logger.info(f"   ✅ Generated {len(chunk_dicts)} embeddings")
                
                # ========================================================
                # Insert into Milvus
                # ========================================================
                
                logger.info("   💾 Storing in Milvus...")
                
                try:
                    result = milvus_store.insert_chunks(chunk_dicts)
                    
                    if result.get("skipped"):
                        logger.warning(f"   ⏭️  Already processed (skipped)")
                        stats["skipped_duplicates"] += 1
                    else:
                        inserted = result.get("inserted", 0)
                        logger.info(f"   ✅ Inserted {inserted} chunks")
                        stats["total_chunks"] += inserted
                        stats["successful"] += 1
                
                except Exception as e:
                    logger.error(f"   ❌ Milvus insertion failed: {e}")
                    failed_files.append((clean_name, f"Milvus error: {str(e)[:50]}"))
                    stats["failed"] += 1
                    continue
                
                logger.info(f"   ✅ Completed {clean_name}")
            
            except Exception as e:
                logger.error(f"   ❌ Unexpected error processing {clean_name}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                failed_files.append((clean_name, f"Unexpected: {str(e)[:50]}"))
                stats["failed"] += 1
                continue
        
        # ============================================================
        # STEP 5: Final Statistics
        # ============================================================
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        logger.info("\n" + "=" * 70)
        logger.info("📊 FINAL STATISTICS")
        logger.info("=" * 70)
        logger.info(f"   Total files:       {stats['total_files']}")
        logger.info(f"   ✅ Successful:      {stats['successful']}")
        logger.info(f"   ❌ Failed:          {stats['failed']}")
        logger.info(f"   ⏭️  Skipped (dup):   {stats['skipped_duplicates']}")
        logger.info(f"   📝 Total chunks:    {stats['total_chunks']}")
        logger.info(f"   ⏱️  Duration:        {duration}")
        logger.info(f"   📅 Completed:       {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Failed files
        if failed_files:
            logger.info("\n" + "=" * 70)
            logger.info("❌ FAILED FILES")
            logger.info("=" * 70)
            for fname, reason in failed_files:
                logger.info(f"   • {fname}: {reason}")
        
        # Milvus stats
        logger.info("\n" + "=" * 70)
        logger.info("💾 MILVUS COLLECTION STATS")
        logger.info("=" * 70)
        milvus_stats = milvus_store.get_stats()
        for key, value in milvus_stats.items():
            logger.info(f"   {key}: {value}")
        
        # Cleanup
        milvus_store.close()
        
        logger.info("\n" + "=" * 70)
        logger.info("🎉 PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)
    
    except Exception as e:
        logger.error(f"\n❌ PIPELINE FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


# -------------------------------------------------
# Entry Point
# -------------------------------------------------

if __name__ == "__main__":
    import sys
    
    # Get limit from command line or use default
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 53
    
    logger.info(f"\nProcessing {limit} files...")
    run_pipeline(limit=limit)'''
"""
Production Lovdata Ingestion Pipeline - TOKEN-AWARE VERSION
Complete integration with Milvus storage and XML processing

Flow:
1. Load XML files from local folder
2. Convert XML → clean text (with metadata extraction)
3. Token-aware chunking (max 512 tokens, sentence boundaries, overlap)
4. Batch embedding generation (configurable batch size)
5. Store in Milvus (vectors + metadata + URL)

Key Features:
✅ Token-based chunking (no truncation, no data loss)
✅ Smart sentence-boundary splitting
✅ Context preservation with overlap
✅ Batch processing for efficiency
✅ Automatic retry on failures
✅ VRAM-safe configuration
"""

import gc
import os
import sys
import logging
import hashlib
from datetime import datetime
from pathlib import Path

import torch
from ingestion.src.processors.chunker import NorwegianLovdataChunker, TokenCounter
from ingestion.src.processors.embedder_sagemaker import SageMakerBGEEmbedder

# Import your existing components
from ingestion.src.processors.text_processor import process_xml_to_text
from ingestion.src.storage.milvus_store import MilvusLovdataStore

# -------------------------------------------------
# Configuration
# -------------------------------------------------

# Paths
RAW_XML_DIR = Path("data/raw_xml")
ARCHIVE_NAME = "local_raw_xml"
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "pipeline_token_aware.log"
# Milvus configuration
MILVUS_HOST = "13.204.226.35"
MILVUS_PORT = 19530
MILVUS_COLLECTION = "lovdata_hierarchical_chunks"

# Token-aware chunking configuration
MAX_TOKENS_PER_CHUNK = 480      # Safe for BGE-M3 embedder
OVERLAP_TOKENS = 50             # Context preservation between chunks

# Batch processing configuration
BATCH_SIZE = 1                  # Process 5 chunks at once
CHUNK_DELAY = 1.0               # Delay between batches (seconds)
MAX_RETRIES = 3                 # Retry attempts on failure
RETRY_DELAY = 15                # Initial retry delay (seconds)

# SageMaker configuration
SAGEMAKER_ENDPOINT = os.getenv("SAGEMAKER_ENDPOINT", "embedding-bge-m3-endpoint")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

# -------------------------------------------------
# Logging Setup
# -------------------------------------------------

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ],
    force=True
)

logger = logging.getLogger("lovdata-token-aware")


# -------------------------------------------------
# Helper Functions
# -------------------------------------------------

def calculate_file_hash(content: str) -> str:
    """Calculate SHA-256 hash of file content"""
    try:
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    except Exception as e:
        logger.error(f"Error hashing content: {e}")
        return hashlib.sha256(b"error").hexdigest()


def print_pipeline_header():
    """Print pipeline startup information"""
    logger.info("=" * 70)
    logger.info("🚀 LOVDATA TOKEN-AWARE INGESTION PIPELINE")
    logger.info("=" * 70)
    logger.info(f"   Configuration:")
    logger.info(f"   • Max tokens per chunk: {MAX_TOKENS_PER_CHUNK}")
    logger.info(f"   • Overlap tokens: {OVERLAP_TOKENS}")
    logger.info(f"   • Batch size: {BATCH_SIZE}")
    logger.info(f"   • Chunk delay: {CHUNK_DELAY}s")
    logger.info(f"   • Max retries: {MAX_RETRIES}")
    logger.info(f"   • SageMaker endpoint: {SAGEMAKER_ENDPOINT}")
    logger.info(f"   • Milvus: {MILVUS_HOST}:{MILVUS_PORT}/{MILVUS_COLLECTION}")
    logger.info(f"   • Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)


def print_statistics(stats: dict, start_time: datetime, failed_files: list):
    """Print final pipeline statistics"""
    end_time = datetime.now()
    duration = end_time - start_time
    
    logger.info("\n" + "=" * 70)
    logger.info("📊 FINAL STATISTICS")
    logger.info("=" * 70)
    logger.info(f"   Total files:       {stats['total_files']}")
    logger.info(f"   ✅ Successful:      {stats['successful']}")
    logger.info(f"   ❌ Failed:          {stats['failed']}")
    logger.info(f"   ⏭️  Skipped (dup):   {stats['skipped_duplicates']}")
    logger.info(f"   📝 Total chunks:    {stats['total_chunks']}")
    logger.info(f"   ✂️  Split chunks:    {stats['split_chunks']}")
    logger.info(f"   ⏱️  Duration:        {duration}")
    logger.info(f"   📅 Completed:       {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Token-aware benefits
    if stats['split_chunks'] > 0:
        logger.info("\n" + "=" * 70)
        logger.info("✅ TOKEN-AWARE BENEFITS")
        logger.info("=" * 70)
        logger.info(f"   Intelligently split {stats['split_chunks']} oversized chunks")
        logger.info("   ✓ No data loss (vs character truncation)")
        logger.info("   ✓ Preserved sentence boundaries")
        logger.info("   ✓ Maintained context with overlap")
        logger.info("   ✓ VRAM-safe processing")
    
    # Failed files
    if failed_files:
        logger.info("\n" + "=" * 70)
        logger.info("❌ FAILED FILES")
        logger.info("=" * 70)
        for fname, reason in failed_files[:20]:  # Show first 20
            logger.info(f"   • {fname}: {reason}")
        if len(failed_files) > 20:
            logger.info(f"   ... and {len(failed_files) - 20} more")


# -------------------------------------------------
# Main Pipeline
# -------------------------------------------------

def run_pipeline(limit: int = None):
    """
    Complete ingestion pipeline with token-aware chunking
    
    Args:
        limit: Number of files to process (None = all)
    """
    
    start_time = datetime.now()
    print_pipeline_header()
    
    # Statistics tracking
    stats = {
        "total_files": 0,
        "successful": 0,
        "failed": 0,
        "total_chunks": 0,
        "split_chunks": 0,
        "skipped_duplicates": 0
    }
    
    failed_files = []
    
    try:
        # ============================================================
        # STEP 1: Initialize Components
        # ============================================================
        
        logger.info("\n📦 Initializing components...")
        
        # Milvus store (your actual implementation)
        try:
            milvus_store = MilvusLovdataStore(
                milvus_host=MILVUS_HOST,
                milvus_port=MILVUS_PORT,
                collection_name=MILVUS_COLLECTION
            )
            logger.info("   ✅ Milvus store initialized")
        except Exception as e:
            logger.error(f"   ❌ Failed to initialize Milvus: {e}")
            raise
        
        # Token-aware chunker
        try:
            chunker = NorwegianLovdataChunker(
                max_tokens=MAX_TOKENS_PER_CHUNK,
                overlap_tokens=OVERLAP_TOKENS
            )
            logger.info(
                f"   ✅ Token-aware chunker initialized "
                f"(max={MAX_TOKENS_PER_CHUNK}, overlap={OVERLAP_TOKENS})"
            )
        except Exception as e:
            logger.error(f"   ❌ Failed to initialize chunker: {e}")
            raise
        
        # Token-aware embedder with batch processing
        try:
            embedder = SageMakerBGEEmbedder(
                endpoint_name=SAGEMAKER_ENDPOINT,
                region_name=AWS_REGION,
                batch_size=BATCH_SIZE,
                chunk_delay=CHUNK_DELAY,
                max_retries=MAX_RETRIES,
                retry_delay=RETRY_DELAY,
                warn_token_threshold=MAX_TOKENS_PER_CHUNK
            )
            logger.info(
                f"   ✅ Token-aware embedder initialized "
                f"(batch={BATCH_SIZE}, delay={CHUNK_DELAY}s)"
            )
        except Exception as e:
            logger.error(f"   ❌ Failed to initialize embedder: {e}")
            raise
        
        # ============================================================
        # STEP 2: Load XML Files
        # ============================================================
        
        logger.info("\n📥 Loading XML files from local folder...")
        
        if not RAW_XML_DIR.exists():
            raise RuntimeError(f"Directory not found: {RAW_XML_DIR}")
        
        xml_files = sorted(RAW_XML_DIR.glob("*.xml"))
        
        if not xml_files:
            raise RuntimeError(f"No XML files found in {RAW_XML_DIR}")
        
        if limit:
            xml_files = xml_files[:limit]
            logger.info(f"   📌 Limited to first {limit} files")
        
        logger.info(f"   ✅ Found {len(xml_files)} XML files")
        
        # ============================================================
        # STEP 3: Convert XML to Clean Text
        # ============================================================
        
        logger.info("\n🔄 Converting XML to clean text...")
        
        try:
            documents = process_xml_to_text(xml_files, max_workers=4)
            logger.info(f"   ✅ Converted {len(documents)} documents")
        except Exception as e:
            logger.error(f"   ❌ XML processing failed: {e}")
            raise
        
        if not documents:
            raise RuntimeError("No valid documents after XML processing")
        
        stats["total_files"] = len(documents)
        
        # ============================================================
        # STEP 4: Process Each Document (Token-Aware)
        # ============================================================
        
        logger.info("\n" + "=" * 70)
        logger.info("📊 PROCESSING DOCUMENTS (TOKEN-AWARE)")
        logger.info("=" * 70)
        
        for idx, doc in enumerate(documents, 1):
            try:
                # Memory cleanup
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                
                # Extract document data
                file_name = doc["file_name"]
                clean_name = file_name.replace(".xml", "").replace(".txt", "")
                text = doc["text"]
                metadata = doc.get("metadata", {})
                url = metadata.get("url", "")
                
                logger.info(f"\n[{idx}/{len(documents)}] 📄 {clean_name}")
                logger.info("-" * 70)
                
                # Validate document
                if not text or len(text.strip()) < 50:
                    logger.warning("   ⚠️  Document too short, skipping")
                    failed_files.append((clean_name, "Document too short"))
                    stats["failed"] += 1
                    continue
                
                # Calculate file hash
                file_hash = calculate_file_hash(text)
                logger.debug(f"   File hash: {file_hash[:16]}...")
                
                # ========================================================
                # TOKEN-AWARE CHUNKING
                # ========================================================
                
                logger.info(f"   ✂️  Token-aware chunking (max={MAX_TOKENS_PER_CHUNK} tokens)...")
                
                try:
                    doc_metadata, chunks = chunker.chunk_text(
                        text=text,
                        file_name=clean_name,
                        zip_name=ARCHIVE_NAME,
                        url=url
                    )
                except Exception as e:
                    logger.error(f"   ❌ Chunking failed: {e}")
                    failed_files.append((clean_name, f"Chunking error: {str(e)[:50]}"))
                    stats["failed"] += 1
                    continue
                
                # Filter valid chunks
                valid_chunks = [c for c in chunks if c.text and c.text.strip()]
                
                if not valid_chunks:
                    logger.warning("   ⚠️  No valid chunks created, skipping")
                    failed_files.append((clean_name, "No valid chunks"))
                    stats["failed"] += 1
                    continue
                
                # Get chunk statistics
                chunk_stats = chunker.get_statistics(valid_chunks)
                stats["split_chunks"] += chunk_stats.get("split_chunks", 0)
                
                logger.info(
                    f"   ✅ Created {len(valid_chunks)} chunks "
                    f"({chunk_stats.get('split_chunks', 0)} were split)"
                )
                logger.info(
                    f"      Avg tokens: {chunk_stats.get('avg_token_count', 0):.0f}, "
                    f"Max tokens: {chunk_stats.get('max_token_count', 0)}, "
                    f"Avg length: {chunk_stats.get('avg_chunk_length', 0):.0f} chars"
                )
                
                # ========================================================
                # Prepare Chunk Payload for Milvus
                # ========================================================
                
                chunk_dicts = []
                for i, chunk in enumerate(valid_chunks):
                    chunk_dict = {
                        "stable_chunk_id": chunk.chunk_id,
                        "file_name": clean_name,
                        "file_hash": file_hash,
                        "chunk_index": i,
                        "parent_index": chunk.parent_index,
                        "child_index": chunk.child_index,
                        "parent_type": chunk.parent_type,
                        "parent_title": chunk.parent_title,
                        "text": chunk.text,
                        "url": url,  # From XML metadata
                        "token_count": chunk.token_count,
                        "is_split": chunk.is_split,
                        "split_index": chunk.split_index
                    }
                    
                    # Add document metadata if available
                    if chunk.metadata:
                        chunk_dict["metadata"] = chunk.metadata
                    
                    chunk_dicts.append(chunk_dict)
                
                # ========================================================
                # BATCH EMBEDDING GENERATION
                # ========================================================
                
                logger.info(
                    f"   🧠 Generating embeddings (batch_size={BATCH_SIZE})..."
                )
                
                try:
                    chunk_dicts = embedder.embed_chunks(chunk_dicts)
                except Exception as e:
                    logger.error(f"   ❌ Embedding generation failed: {e}")
                    failed_files.append((clean_name, f"Embedding error: {str(e)[:50]}"))
                    stats["failed"] += 1
                    continue
                
                # Filter chunks with successful embeddings
                valid_embeddings = [c for c in chunk_dicts if c.get("embedding") is not None]
                
                if not valid_embeddings:
                    logger.error("   ❌ No valid embeddings returned")
                    failed_files.append((clean_name, "No embeddings"))
                    stats["failed"] += 1
                    continue
                
                success_rate = len(valid_embeddings) / len(chunk_dicts) * 100
                logger.info(
                    f"   ✅ Generated {len(valid_embeddings)}/{len(chunk_dicts)} embeddings "
                    f"({success_rate:.1f}%)"
                )
                
                # ========================================================
                # Insert into Milvus
                # ========================================================
                
                logger.info("   💾 Storing in Milvus...")
                
                try:
                    result = milvus_store.insert_chunks(valid_embeddings)
                    
                    if result.get("skipped"):
                        logger.warning("   ⏭️  Already processed (skipped)")
                        stats["skipped_duplicates"] += 1
                    else:
                        inserted = result.get("inserted", 0)
                        logger.info(f"   ✅ Inserted {inserted} chunks into Milvus")
                        stats["total_chunks"] += inserted
                        stats["successful"] += 1
                
                except Exception as e:
                    logger.error(f"   ❌ Milvus insertion failed: {e}")
                    failed_files.append((clean_name, f"Milvus error: {str(e)[:50]}"))
                    stats["failed"] += 1
                    continue
                
                logger.info(f"   ✅ Completed {clean_name}")
            
            except Exception as e:
                logger.error(f"   ❌ Unexpected error processing {clean_name}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                failed_files.append((clean_name, f"Unexpected: {str(e)[:50]}"))
                stats["failed"] += 1
                continue
        
        # ============================================================
        # STEP 5: Final Statistics and Cleanup
        # ============================================================
        
        print_statistics(stats, start_time, failed_files)
        
        # Milvus collection stats
        logger.info("\n" + "=" * 70)
        logger.info("💾 MILVUS COLLECTION STATS")
        logger.info("=" * 70)
        try:
            milvus_stats = milvus_store.get_stats()
            for key, value in milvus_stats.items():
                logger.info(f"   {key}: {value}")
        except Exception as e:
            logger.error(f"   Failed to get Milvus stats: {e}")
        
        # Cleanup
        try:
            milvus_store.close()
        except Exception as e:
            logger.error(f"   Error closing Milvus: {e}")
        
        logger.info("\n" + "=" * 70)
        logger.info("🎉 TOKEN-AWARE PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)
        
        # Return stats for programmatic access
        return {
            "success": True,
            "stats": stats,
            "failed_files": failed_files,
            "duration": datetime.now() - start_time
        }
    
    except Exception as e:
        logger.error(f"\n❌ PIPELINE FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        return {
            "success": False,
            "error": str(e),
            "stats": stats,
            "failed_files": failed_files,
            "duration": datetime.now() - start_time
        }


# -------------------------------------------------
# Entry Point
# -------------------------------------------------

if __name__ == "__main__":
    # Parse command line arguments
    limit = None
    
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
            logger.info(f"\n📌 Processing limited to {limit} files")
        except ValueError:
            logger.error("Invalid limit argument. Usage: python main.py [limit]")
            sys.exit(1)
    else:
        logger.info("\n📌 Processing all available files")
    
    # Run pipeline
    result = run_pipeline(limit=limit)
    
    # Exit with appropriate code
    sys.exit(0 if result["success"] else 1)