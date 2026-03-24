import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# -------------------------------------------------
# Load environment variables
# -------------------------------------------------
load_dotenv()

BASE_DIR = Path(sys.path[0])

# -------------------------------------------------
# Directories
# -------------------------------------------------
RAW_XML_DIR = BASE_DIR / "data" / "raw_xml"
CLEAN_TEXT_DIR = BASE_DIR / "data" / "cleaned_text"
CHECKPOINT_DIR = BASE_DIR / "data" / "checkpoints"
LOG_DIR = BASE_DIR / "logs"

for d in [RAW_XML_DIR, CLEAN_TEXT_DIR, CHECKPOINT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------
# External Services
# -------------------------------------------------
LOVDATA_API_URL = os.getenv("LOVDATA_API_URL", "")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "")

# -------------------------------------------------
# Milvus Configuration (SAFE DEFAULTS)
# -------------------------------------------------
MILVUS_HOST = os.getenv("MILVUS_HOST")

MILVUS_PORT = int(os.getenv("MILVUS_PORT"))

MILVUS_COLLECTION = os.getenv(
    "MILVUS_COLLECTION"  # ✅ safe default
)

MILVUS_INDEX_TYPE = os.getenv("MILVUS_INDEX_TYPE", "HNSW")
MILVUS_METRIC_TYPE = os.getenv("MILVUS_METRIC_TYPE", "COSINE")
MILVUS_NLIST = int(os.getenv("MILVUS_NLIST", "1024"))

# -------------------------------------------------
# Chunking / Embedding
# -------------------------------------------------
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

EMBED_MODEL = os.getenv("EMBED_MODEL")

# -------------------------------------------------
# Logging
# -------------------------------------------------
import logging

LOG_FILE = LOG_DIR / "ingestion.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("lovdata-ingestion")

# -------------------------------------------------
# Validation (ONLY WHAT IS REALLY REQUIRED)
# -------------------------------------------------
if not MILVUS_COLLECTION.strip():
    raise RuntimeError("❌ MILVUS_COLLECTION missing or invalid")

if __name__ == "__main__":
    logger.info("✅ Configuration loaded successfully")
    logger.info(f"Milvus → {MILVUS_HOST}:{MILVUS_PORT}")
    logger.info(f"Collection → {MILVUS_COLLECTION}")
