import os
from dotenv import load_dotenv
import sys
from pathlib import Path
load_dotenv()

BASE_DIR = Path(os.path.join(sys.path[0],"ingestion"))
# ============================
# Directories
# ============================
RAW_XML_DIR = os.path.join(BASE_DIR, "data/raw_xml")
CLEAN_TEXT_DIR = os.path.join(BASE_DIR, "data/cleaned_text")
CHECKPOINT_DIR = os.path.join(BASE_DIR, "data/checkpoints")
LOG_DIR = os.path.join(BASE_DIR, "logs")

os.makedirs(RAW_XML_DIR, exist_ok=True)
os.makedirs(CLEAN_TEXT_DIR, exist_ok=True)
os.makedirs(CHECKPOINT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

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
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")

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

LOG_FILE = os.path.join(LOG_DIR, "ingestion.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("lovdata-ingestion")

if __name__ == "__main__":
    logger.info("✅ Configuration loaded successfully")
    logger.info(f"Milvus → {MILVUS_HOST}:{MILVUS_PORT}, collection={MILVUS_COLLECTION}")