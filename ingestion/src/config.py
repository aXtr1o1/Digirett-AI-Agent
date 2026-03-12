import os
from dotenv import load_dotenv
from pathlib import Path
import logging
#-------------------------------------------------
# Load environment variables
# -------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# Base directories
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_XML_DIR    = BASE_DIR / "data" / "raw_xml"
CLEAN_TEXT_DIR = BASE_DIR / "data" / "cleaned_text"
CHECKPOINT_DIR = BASE_DIR / "data" / "checkpoints"
ARCHIVE_DIR    = BASE_DIR / "data" / "archives"
LOG_DIR        = BASE_DIR / "logs"

 
for _d in [RAW_XML_DIR, CLEAN_TEXT_DIR, CHECKPOINT_DIR, LOG_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# Ensure log directory exists BEFORE logging
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ============================
# Excel Dataset Folder
# ============================

XL_DATASET_FOLDER = os.getenv("XL_DATASET_FOLDER")

if not XL_DATASET_FOLDER:
    raise RuntimeError("XL_DATASET_FOLDER missing in .env")

XL_DATASET_FOLDER = Path(XL_DATASET_FOLDER)

if not XL_DATASET_FOLDER.exists():
    raise RuntimeError(f"XL_DATASET_FOLDER path does not exist → {XL_DATASET_FOLDER}")

# ============================
# External Services
# ============================
LOVDATA_API_URL      = os.getenv("LOVDATA_API_URL", "")
LOVDATA_GET_ENDPOINT = "/get"

SUPABASE_URL         = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_BUCKET      = os.getenv("SUPABASE_BUCKET", "")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE")

# ============================
# Azure OpenAI / Embedding
# ============================
EMBEDDING_PROVIDER      = os.getenv("EMBEDDING_PROVIDER", "azure_openai")
EMBEDDING_MODEL         = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSION     = int(os.getenv("EMBEDDING_DIMENSION", "1536"))

AZURE_OPENAI_ENDPOINT   = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY        = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

# ============================
# Chunking
# ============================
MAX_TOKENS_PER_CHUNK = int(os.getenv("MAX_TOKENS_PER_CHUNK", "512"))
OVERLAP_TOKENS       = int(os.getenv("OVERLAP_TOKENS", "50"))
CHUNK_SIZE           = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP        = int(os.getenv("CHUNK_OVERLAP", "200"))

# ============================
# Embedding Batching
# ============================
EMBEDDING_BATCH_SIZE  = int(os.getenv("EMBEDDING_BATCH_SIZE", "4"))
EMBEDDING_CHUNK_DELAY = float(os.getenv("EMBEDDING_CHUNK_DELAY", "0.5"))
CHUNK_DELAY           = float(os.getenv("EMBEDDING_CHUNK_DELAY", "1.0"))

# ============================
# Milvus Connection
# ============================
MILVUS_HOST        = os.getenv("MILVUS_HOST", "")
MILVUS_PORT        = int(os.getenv("MILVUS_PORT", "19530"))
MILVUS_DIMENSION   = int(os.getenv("MILVUS_DIMENSION", str(EMBEDDING_DIMENSION)))
MILVUS_COLLECTION  = os.getenv("MILVUS_COLLECTION")
MILVUS_INDEX_TYPE  = os.getenv("MILVUS_INDEX_TYPE", "HNSW")
MILVUS_METRIC_TYPE = os.getenv("MILVUS_METRIC_TYPE", "IP")
MILVUS_NLIST       = int(os.getenv("MILVUS_NLIST", "1536"))

# ============================
# Milvus Insert Throttling
# ============================
# Rows per gRPC sub-batch — smaller batches cause smaller CPU spikes per call
MILVUS_INSERT_BATCH   = int(os.getenv("MILVUS_INSERT_BATCH", "500"))
# Sleep between Milvus sub-batches (seconds)
MILVUS_INSERT_SLEEP   = float(os.getenv("MILVUS_INSERT_SLEEP", "0"))
# Connection timeout (seconds) — increased for flaky networks
MILVUS_CONNECT_TIMEOUT = int(os.getenv("MILVUS_CONNECT_TIMEOUT", "90"))
# How many total inserts between periodic flushes
MILVUS_FLUSH_EVERY    = int(os.getenv("MILVUS_FLUSH_EVERY", "5000"))

# ============================
# Milvus CPU Thresholds
# ============================
MILVUS_CPU_WARN_THRESHOLD = int(os.getenv("MILVUS_CPU_WARN_THRESHOLD", "65"))
MILVUS_CPU_PAUSE_THRESHOLD = int(os.getenv("MILVUS_CPU_PAUSE_THRESHOLD", "70"))
MILVUS_CPU_MAX_WAIT       = int(os.getenv("MILVUS_CPU_MAX_WAIT", "60"))
MILVUS_MEM_WARN_THRESHOLD = int(os.getenv("MILVUS_MEM_WARN_THRESHOLD", "80"))
MILVUS_LOG_PAYLOAD        = os.getenv("MILVUS_LOG_PAYLOAD", "true").lower() == "true"

# ============================
# Embedder CPU Thresholds
# ============================
# Pause before next embedding batch if CPU exceeds this %
EMBED_CPU_PAUSE_THRESHOLD = int(os.getenv("EMBED_CPU_PAUSE_THRESHOLD", "70"))
# How long to pause (seconds)
EMBED_CPU_PAUSE_SECS      = float(os.getenv("EMBED_CPU_PAUSE_SECS", "3.0"))

# ============================
# Pipeline (main.py) CPU Thresholds
# ============================
# Log a warning when CPU exceeds this %
PIPELINE_CPU_WARN  = int(os.getenv("PIPELINE_CPU_WARN", "65"))
# Sleep 3 s when CPU exceeds this %
PIPELINE_CPU_PAUSE = int(os.getenv("PIPELINE_CPU_PAUSE", "75"))
# Sleep 8 s when CPU exceeds this %
PIPELINE_CPU_MAX   = int(os.getenv("PIPELINE_CPU_MAX", "85"))
# Mandatory sleep between every processed document (seconds)
PIPELINE_DOC_SLEEP = float(os.getenv("PIPELINE_DOC_SLEEP", "0.3"))

# ============================
# XML Processing
# ============================
# Parallel workers for XML → text (keep at 2 to avoid fork-induced CPU spike)
XML_PROCESS_WORKERS = int(os.getenv("XML_PROCESS_WORKERS", "2"))

# ============================
# Scheduler
# ============================
SCHEDULER_BATCH_SIZE  = int(os.getenv("SCHEDULER_BATCH_SIZE", "50"))
SCHEDULER_CRON_HOUR   = int(os.getenv("SCHEDULER_CRON_HOUR", "2"))
SCHEDULER_CRON_MINUTE = int(os.getenv("SCHEDULER_CRON_MINUTE", "0"))
SCHEDULER_API_TIMEOUT = int(os.getenv("SCHEDULER_API_TIMEOUT", "30"))

# ============================
# Validation
# ============================
if not LOVDATA_API_URL:
    raise RuntimeError("LOVDATA_API_URL missing from environment")
if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL missing from environment")
if not SUPABASE_SERVICE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_KEY missing from environment")
if not SUPABASE_BUCKET:
    raise RuntimeError("SUPABASE_BUCKET missing from environment")
if not SUPABASE_TABLE:
    raise ValueError("SUPABASE_TABLE not found in environment variables")
if not MILVUS_COLLECTION or not MILVUS_COLLECTION.strip():
    raise RuntimeError("MILVUS_COLLECTION missing or invalid")

# ============================
# Logging
# ============================
LOG_FILE = LOG_DIR / "ingestion.log"

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

if __name__ == "__main__":
    logger.info("✅ Configuration loaded successfully")
    logger.info(f"Milvus → {MILVUS_HOST}:{MILVUS_PORT}, collection={MILVUS_COLLECTION}")