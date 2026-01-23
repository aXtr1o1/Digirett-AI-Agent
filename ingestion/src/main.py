from ingestion.src.processors.chunker import NorwegianLovdataChunker
from ..collectors.lovdata_collector import fetch_lovdata_files
from .processors.text_processor import process_xml_to_text
from  ingestion.src.storage.supabase_store import SupabaseStore
from datetime import datetime
from ingestion.src.config import LOG_FILE, logger

from ingestion.src.config import CHECKPOINT_DIR

import os
import json
from datetime import datetime
import logging
from time import sleep
# --------------------------------------------------
# Logging
# --------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ],
    force=True # This is critical to override sub-module configs
)
logger = logging.getLogger("lovdata-ingestion")

CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, "ingestion_state.json")


# --------------------------------------------------
# Checkpoint helpers
# --------------------------------------------------
def load_checkpoint():
   
    if not os.path.exists(CHECKPOINT_FILE):
        
        return {}

    try:
        with open(CHECKPOINT_FILE, "r") as f:
            content = f.read().strip()
            
            return json.loads(content) if content else {}
    except Exception as e:
        logger.warning(f"⚠️ Invalid checkpoint file, ignoring it: {e}")
        return {}


def save_checkpoint(data):
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    tmp_file = CHECKPOINT_FILE + ".tmp"

    with open(tmp_file, "w") as f:
        json.dump(data, f, indent=2)

    os.replace(tmp_file, CHECKPOINT_FILE)


# --------------------------------------------------
# Pipeline
# --------------------------------------------------
# ingestion/src/main.py

def run_pipeline(limit: int = 200):
    logger.info("🚀 Starting Pipeline: Storage -> Hierarchical Chunking")
    db_store = SupabaseStore()
    chunker = NorwegianLovdataChunker()

    try:
        # STEP 1: Fetch local XML files
        xml_files, archive_name = fetch_lovdata_files(limit=limit)
        
        # STEP 2: XML → Structured Text (Batch Process)
        documents = process_xml_to_text(xml_files)
        logger.info(f"🧹 Converted {len(documents)} files to text.")

        # STEP 3: Integrated Storage and Chunking Loop
        processed_count = 0
        total_chunks_created = 0

        all_chunk_data = [] # List to collect results

        for doc in documents:
            # 3a. Find original XML path
            xml_filename = doc['file_name'].replace('.txt', '.xml')
            xml_path = next((p for p in xml_files if xml_filename in p), None)

            if not xml_path:
                continue

            # 3b. Run Hierarchical Chunking first to get the File Hash
            # This ensures the hash in the DB matches the chunks
            doc_metadata, chunks = chunker.chunk_text(
                text=doc['text'], 
                file_name=doc['file_name'],
                zip_name=archive_name
            )

            chunker.log_file_summary(doc_metadata, chunks)

            all_chunk_data.append({
                "file_name": doc['file_name'],
                "file_hash": doc_metadata.file_hash,
                "chunks": [c.to_dict() for c in chunks]
            })

            # 3c. Store XML in Supabase Storage and Table
            if db_store.upload_xml_and_log(
                file_path=xml_path, 
                zip_name=archive_name,
                file_hash=doc_metadata.file_hash 
            ):
                processed_count += 1
                total_chunks_created += len(chunks)
                logger.info(f"✅ Processed {doc['file_name']}: {len(chunks)} chunks.")

        # 3. ADD: Save results to JSON after loop finishes
        logger.info(f"💾 Verification file created: {len(all_chunk_data)} files exported.")

        # STEP 4: Final Checkpoint
        save_checkpoint({
            "last_run": datetime.utcnow().isoformat(),
            "files_processed": processed_count,
            "total_chunks": total_chunks_created,
            "status": "storage_and_chunking_complete"
        })
        
        logger.info(f"🎉 Pipeline Complete: {processed_count} files stored, {total_chunks_created} chunks mapped.")

    except Exception as e:
        logger.exception("❌ Pipeline failed")
        raise

if __name__ == "__main__":
    run_pipeline(limit=200)