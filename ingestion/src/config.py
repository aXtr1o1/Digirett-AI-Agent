import os
from dotenv import load_dotenv
import sys
from pathlib import Path
#-------------------------------------------------
# Load environment variables
# -------------------------------------------------
load_dotenv()

# 🔒 FIXED BASE DIR
BASE_DIR = Path(__file__).resolve().parents[1]

RAW_XML_DIR = BASE_DIR / "data" / "raw_xml"
CLEAN_TEXT_DIR = BASE_DIR / "data" / "cleaned_text"
CHECKPOINT_DIR = BASE_DIR / "data" / "checkpoints"
LOG_DIR = BASE_DIR / "logs"

for d in [RAW_XML_DIR, CLEAN_TEXT_DIR, CHECKPOINT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Ensure log directory exists BEFORE logging
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ============================
# External Services
# ============================
LOVDATA_API_URL = os.getenv("LOVDATA_API_URL")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")

# ============================
# Milvus Configuration
# ============================
MILVUS_HOST = os.getenv("MILVUS_HOST")
MILVUS_PORT = int(os.getenv("MILVUS_PORT"))

MILVUS_COLLECTION = os.getenv(
    "MILVUS_COLLECTION"  # ✅ SAFE DEFAULT
)

MILVUS_INDEX_TYPE = os.getenv("MILVUS_INDEX_TYPE", "HNSW")
MILVUS_METRIC_TYPE = os.getenv("MILVUS_METRIC_TYPE", "COSINE")
MILVUS_NLIST = int(os.getenv("MILVUS_NLIST", "1024"))

# ============================
# Chunking / Embedding
# ============================

MAX_TOKENS_PER_CHUNK = int(os.getenv("MAX_TOKENS_PER_CHUNK", "512"))
OVERLAP_TOKENS = int(os.getenv("OVERLAP_TOKENS", "50"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "5"))
EMBEDDING_CHUNK_DELAY = float(os.getenv("EMBEDDING_CHUNK_DELAY", "0.5"))

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

EMBED_MODEL = os.getenv("EMBED_MODEL")

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")


# ============================
# Validation (IMPORTANT)
# ============================
if not LOVDATA_API_URL:
    raise RuntimeError("LOVDATA_API_URL missing")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL missing")

if not SUPABASE_SERVICE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_KEY missing")

if not SUPABASE_BUCKET:
    raise RuntimeError("SUPABASE_BUCKET missing")

if not MILVUS_COLLECTION or not MILVUS_COLLECTION.strip():
    raise RuntimeError("MILVUS_COLLECTION missing or invalid")

# ============================
# Logging Configuration
# ============================
import logging

LOG_FILE = LOG_DIR / "ingestion.log"

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

if __name__ == "__main__":
    logger.info("✅ Configuration loaded successfully")
    logger.info(f"Milvus → {MILVUS_HOST}:{MILVUS_PORT}, collection={MILVUS_COLLECTION}")