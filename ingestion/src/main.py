import gc
import os
import sys
import torch
import logging
import hashlib
from datetime import datetime

from ingestion.src.processors.chunker import NorwegianLovdataChunker
from ingestion.src.processors.embedder import BGEEmbeddingGenerator
from ingestion.collectors.lovdata_collector import fetch_lovdata_files
from ingestion.src.processors.text_processor import process_xml_to_text
from ingestion.src.storage.supabase_store import SupabaseStore
from ingestion.src.storage.milvus_store import MilvusLovdataStore
from ingestion.src.config import (
    LOG_FILE,
    MILVUS_HOST,
    MILVUS_PORT,
    MILVUS_COLLECTION
)

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

def run_pipeline(limit: int = 200):
    logger.info("🚀 Lovdata ingestion started")

    db_store = SupabaseStore()
    chunker = NorwegianLovdataChunker()

    milvus_store = MilvusLovdataStore(
        MILVUS_HOST,
        MILVUS_PORT,
        MILVUS_COLLECTION
    )

    embedder = BGEEmbeddingGenerator(
        model_name="BAAI/bge-m3",
        embedding_type="dense",
        use_fp16=True
    )

    xml_files, archive_name = fetch_lovdata_files(limit=limit)
    documents = process_xml_to_text(xml_files)

    for idx, doc in enumerate(documents, 1):
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        clean_name = doc["file_name"].split(".")[0]
        xml_path = next(p for p in xml_files if clean_name in p)

        file_hash = db_store.calculate_hash(xml_path)
        file_size = os.path.getsize(xml_path)

        logger.info(f"[{idx}] Processing {clean_name}")

        # 1️⃣ Upload XML to storage (NO extension)
        storage_uri = db_store.upload_xml_to_storage(xml_path, clean_name)

        # 2️⃣ Chunk text
        _, chunks = chunker.chunk_text(
            doc["text"],
            clean_name,
            archive_name
        )

        texts = [c.text for c in chunks if c.text and c.text.strip()]

        if not texts:
            logger.warning(f"⚠️ No valid chunks for {clean_name}, skipping embedding & DB insert")
            continue

        vectors = embedder._encode_batch(texts)["dense_vecs"]


        payload = []
        valid_chunks = [c for c in chunks if c.text and c.text.strip()]

        for i, chunk in enumerate(valid_chunks):
            payload.append({
                "stable_chunk_id": chunk.chunk_id,
                "file_name": clean_name,
                "file_hash": file_hash,
                "chunk_index": i,
                "parent_index": chunk.parent_index,
                "child_index": chunk.child_index,
                "parent_type": chunk.parent_type,
                "parent_title": chunk.parent_title,
                "text": chunk.text,
                "embedding": vectors[i].tolist()
            })

        # 3️⃣ Insert into Milvus
        result = milvus_store.insert_chunks(payload)

        if result.get("skipped"):
            logger.warning(f"⏭️ Skipped duplicate {clean_name}")
            continue

        # 4️⃣ Insert Supabase metadata (AFTER Milvus success)
        db_store.insert_file_metadata(
            zip_name=archive_name,
            file_name=clean_name,
            file_hash=file_hash,
            file_size=file_size,
            file_storage_uri=storage_uri
        )


        logger.info(f"✅ Completed {clean_name}")

    milvus_store.close()
    logger.info("🎉 Pipeline completed successfully")

if __name__ == "__main__":
    run_pipeline(limit=200)