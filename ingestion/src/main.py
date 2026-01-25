import gc
import os
import json
import logging
import torch 
import sys
import hashlib
from datetime import datetime
from typing import Set

# Import project-specific modules
from ingestion.src.processors.chunker import NorwegianLovdataChunker
from ingestion.src.processors.embedder import BGEEmbeddingGenerator
from ingestion.collectors.lovdata_collector import fetch_lovdata_files
from ingestion.src.processors.text_processor import process_xml_to_text
from ingestion.src.storage.supabase_store import SupabaseStore
from ingestion.src.config import LOG_FILE, CHECKPOINT_DIR

# NEW: Import your updated Milvus Store
from ingestion.src.storage.milvus_store import MilvusLovdataStore

# --------------------------------------------------
# Logging Configuration
# --------------------------------------------------
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

CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, "ingestion_state.json")

# --------------------------------------------------
# Checkpoint Helpers
# --------------------------------------------------
def save_checkpoint(data):
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    tmp_file = CHECKPOINT_FILE + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_file, CHECKPOINT_FILE)

# --------------------------------------------------
# Helper: Calculate file hash
# --------------------------------------------------
def calculate_file_hash(file_path: str) -> str:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# --------------------------------------------------
# Pipeline Execution
# --------------------------------------------------

def run_pipeline(limit: int = 200):
    logger.info("🚀 Starting Production Pipeline: XML -> Chunks -> BGE-M3 -> Milvus Cloud")
    
    # Initialize Core Components
    db_store = SupabaseStore()
    chunker = NorwegianLovdataChunker()
    
    # Initialize Milvus Store (Remote Host: 13.204.226.35)
    milvus_store = None
    try:
        from ingestion.src.config import (
            MILVUS_HOST, MILVUS_PORT, MILVUS_COLLECTION,
            SUPABASE_URL, SUPABASE_SERVICE_KEY
        )
        milvus_store = MilvusLovdataStore(
            milvus_host=MILVUS_HOST,
            milvus_port=MILVUS_PORT,
            collection_name=MILVUS_COLLECTION,
            supabase_url=SUPABASE_URL,
            supabase_key=SUPABASE_SERVICE_KEY
        )
        logger.info("✅ Milvus storage initialized and connected to cloud")
    except Exception as e:
        logger.error(f"❌ Milvus initialization failed: {e}")
        sys.exit(1)
    
    # Initialize BGE-M3
    try:
        embedder = BGEEmbeddingGenerator(
            model_name="BAAI/bge-m3",
            embedding_type="dense",
            use_fp16=True 
        )
    except Exception as e:
        logger.error(f"❌ Failed to load BGE-M3 model: {e}")
        sys.exit(1)
    
    try:
        # STEP 1: Get existing hashes from database
        existing_hashes = milvus_store.get_existing_hashes()
        logger.info(f"📋 Found {len(existing_hashes)} existing file hashes in database")
        
        # STEP 2: Fetch local XML files
        xml_files, archive_name = fetch_lovdata_files(limit=limit)
        
        # STEP 3: Filter out files that already exist (pre-processing deduplication)
        unique_xml_files = []
        skipped_count = 0
        
        for xml_path in xml_files:
            file_hash = calculate_file_hash(xml_path)
            if file_hash not in existing_hashes:
                unique_xml_files.append(xml_path)
            else:
                skipped_count += 1
                logger.info(f"⏭️ Skipping duplicate file: {os.path.basename(xml_path)} (hash: {file_hash[:12]}...)")
        
        logger.info(f"📊 Filtered files: {len(unique_xml_files)} unique, {skipped_count} duplicates skipped")
        
        # STEP 4: Only process unique files up to the limit
        files_to_process = unique_xml_files[:limit]
        
        if len(files_to_process) == 0:
            logger.info("✅ No new files to process. All files already exist in database.")
            return
        
        # STEP 5: XML → Structured Text (only for unique files)
        documents = process_xml_to_text(files_to_process)
        logger.info(f"🧹 Converted {len(documents)} unique files to text.")

        # STEP 6: Integrated processing loop
        processed_count = 0
        total_milvus_inserted = 0 

        for doc in documents:
            # Memory safety - clear cache
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # 1. Clean the filename
            clean_name = doc['file_name'].split('.')[0]
            xml_filename = f"{clean_name}.xml"
            
            # 2. Define the URI and local path
            xml_uri = f"https://xdnqfhqdbsjgfanfbvdp.supabase.co/storage/v1/object/public/lovdata-raw-xml/{xml_filename}"
            xml_path = next((p for p in files_to_process if clean_name in p), None)
            
            if not xml_path:
                logger.warning(f"⚠️ XML path not found for {clean_name}, skipping...")
                continue

            # 3. Get file size and hash for metadata
            current_file_size = os.path.getsize(xml_path)
            current_file_hash = calculate_file_hash(xml_path)

            # 4. Process Chunks & Embedding
            doc_metadata, chunks = chunker.chunk_text(doc['text'], clean_name, archive_name)
            
            chunk_texts = [c.text for c in chunks]
            if not chunk_texts: continue

            output = embedder._encode_batch(chunk_texts)
            vectors = output['dense_vecs']

            # 5. Build Payload with all metadata
            milvus_payload = []
            for i, chunk in enumerate(chunks):
                s_id = f"{current_file_hash[:12]}_{i:06d}"
                
                milvus_payload.append({
                    "stable_chunk_id": s_id,
                    "file_name": clean_name,
                    "file_hash": current_file_hash,
                    "file_size": current_file_size,
                    "zip_name": archive_name,
                    "chunk_index": i,
                    "parent_index": getattr(chunk, 'parent_index', -1),
                    "child_index": getattr(chunk, 'child_index', -1),
                    "embedding": vectors[i].tolist(),
                    "file_storage_uri": xml_uri
                })

            # 6. Execute Storage
            if db_store.upload_xml_to_storage(xml_path, xml_filename):
                result = milvus_store.insert_chunks(milvus_payload)
                processed_count += 1
                total_milvus_inserted += result.get('inserted', 0)
                logger.info(f"✅ [{processed_count}/{len(documents)}] {clean_name} -> {result.get('inserted')} vectors synced.")

        # STEP 7: Final Checkpoint
        save_checkpoint({
            "last_run": datetime.utcnow().isoformat(),
            "files_processed": processed_count,
            "files_skipped": skipped_count,
            "milvus_inserted": total_milvus_inserted,
            "status": "success"
        })
        
        logger.info(f"🎉 Pipeline Complete: {total_milvus_inserted} vectors indexed in Milvus.")
        logger.info(f"📊 Summary: {processed_count} new files processed, {skipped_count} duplicates skipped")

    except Exception as e:
        logger.exception("❌ Pipeline failed during execution")
        raise
    finally:
        if milvus_store:
            milvus_store.close()

if __name__ == "__main__":
    run_pipeline(limit=200)