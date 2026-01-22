from ..collectors.lovdata_collector import fetch_lovdata_files
from .processors.text_processor import process_xml_to_text

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
def run_pipeline(limit: int = 200):
    logger.info("🚀 Lovdata ingestion pipeline started")

    try:
        # STEP 0: checkpoint
        checkpoint = load_checkpoint()
        
        logger.info(f"📌 Previous checkpoint: {checkpoint}")
        sleep(2)
        # STEP 1: fetch XML
        xml_files, archive_name = fetch_lovdata_files(limit=limit)

        if not isinstance(xml_files, list):
            raise TypeError("fetch_lovdata_files() must return List[str]")

        logger.info(f"📥 Fetched {len(xml_files)} XML files from {archive_name}")

        # STEP 2: XML → clean text
        documents = process_xml_to_text(xml_files)
        logger.info(f"🧹 Converted to {len(documents)} cleaned documents")

        # 🛑 STOP PIPELINE HERE (INTENTIONAL)
        logger.info("🛑 Pipeline intentionally stopped after XML → text conversion")

        save_checkpoint({
            "last_run": datetime.utcnow().isoformat(),
            "archive": archive_name,
            "files_converted": len(documents),
            "status": "completed_text_only"
        })

        return  # ⬅️ THIS IS CRITICAL

    except Exception as e:
        logger.exception("❌ Pipeline failed")
        save_checkpoint({
            "last_run": datetime.utcnow().isoformat(),
            "status": "failed",
            "error": str(e)
        })
        raise


if __name__ == "__main__":
    run_pipeline(limit=200)