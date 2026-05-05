# from __future__ import annotations

# import logging
# import os
# from pathlib import Path

# from dotenv import load_dotenv

# # -----------------------------------------------------------------------------
# # Load environment
# # -----------------------------------------------------------------------------

# load_dotenv()


# def _required_env(name: str) -> str:
#     value = os.getenv(name, "").strip()
#     if not value:
#         raise RuntimeError(f"{name} missing")
#     return value


# def _optional_env(name: str, default: str = "") -> str:
#     return os.getenv(name, default).strip()


# def _int_env(name: str, default: int) -> int:
#     value = os.getenv(name, str(default)).strip()
#     return int(value)


# def _float_env(name: str, default: float) -> float:
#     value = os.getenv(name, str(default)).strip()
#     return float(value)


# # -----------------------------------------------------------------------------
# # Base directories
# # -----------------------------------------------------------------------------

# BASE_DIR = Path(__file__).resolve().parent.parent
# DATA_DIR = BASE_DIR / "data"
# LOG_DIR = BASE_DIR / "logs"
# CHECKPOINT_DIR = DATA_DIR / "checkpoints"
# CLEAN_TEXT_DIR = DATA_DIR / "cleaned_text"
# RAW_XML_DIR = DATA_DIR / "raw_xml"
# ARCHIVE_DIR = DATA_DIR / "archives"

# for folder in [DATA_DIR, LOG_DIR, CHECKPOINT_DIR, CLEAN_TEXT_DIR, RAW_XML_DIR, ARCHIVE_DIR]:
#     folder.mkdir(parents=True, exist_ok=True)

# LOG_FILE = LOG_DIR / "ingestion.log"

# # -----------------------------------------------------------------------------
# # Workbook / input
# # -----------------------------------------------------------------------------

# XL_DATASET_FOLDER = Path(_required_env("XL_DATASET_FOLDER"))

# # -----------------------------------------------------------------------------
# # Supabase
# # -----------------------------------------------------------------------------

# SUPABASE_URL = _required_env("SUPABASE_URL")
# SUPABASE_SERVICE_KEY = _required_env("SUPABASE_SERVICE_KEY")
# SUPABASE_BUCKET = _required_env("SUPABASE_BUCKET")

# # Final output metadata table
# SUPABASE_TABLE = _required_env("SUPABASE_TABLE")

# # Source lookup tables
# SUPABASE_SOURCE_TABLE_AI = _required_env("SUPABASE_SOURCE_TABLE_AI")
# SUPABASE_SOURCE_TABLE_PREDEFINED = _required_env("SUPABASE_SOURCE_TABLE_PREDEFINED")

# # New XAPI Ingestion Metadata table
# SUPABASE_RAW_METADATA_TABLE = _optional_env("SUPABASE_RAW_METADATA_TABLE", "raw_ingestion_metadata")


# # -----------------------------------------------------------------------------
# # Azure OpenAI / embeddings
# # -----------------------------------------------------------------------------

# EMBEDDING_PROVIDER = _optional_env("EMBEDDING_PROVIDER", "azure_openai")
# EMBEDDING_MODEL = _optional_env("EMBEDDING_MODEL", "text-embedding-3-small")
# EMBEDDING_DIMENSION = _int_env("EMBEDDING_DIMENSION", 1536)

# AZURE_OPENAI_ENDPOINT = _required_env("AZURE_OPENAI_ENDPOINT")
# AZURE_OPENAI_KEY = _required_env("AZURE_OPENAI_KEY")
# AZURE_OPENAI_API_VERSION = _required_env("AZURE_OPENAI_API_VERSION")
# AZURE_OPENAI_DEPLOYMENT = _required_env("AZURE_OPENAI_DEPLOYMENT")

# EMBEDDING_BATCH_SIZE = _int_env("EMBEDDING_BATCH_SIZE", 4)
# EMBEDDING_CHUNK_DELAY = _float_env("EMBEDDING_CHUNK_DELAY", 0.5)

# # -----------------------------------------------------------------------------
# # Chunking
# # -----------------------------------------------------------------------------

# MAX_TOKENS_PER_CHUNK = _int_env("MAX_TOKENS_PER_CHUNK", 512)
# OVERLAP_TOKENS = _int_env("OVERLAP_TOKENS", 50)
# CHUNK_SIZE = _int_env("CHUNK_SIZE", 1000)
# CHUNK_OVERLAP = _int_env("CHUNK_OVERLAP", 200)

# # New section-aware chunker settings
# MAX_CHUNK_SIZE_CHARS = _int_env("MAX_CHUNK_SIZE_CHARS", 12000)
# MILVUS_TEXT_LIMIT = _int_env("MILVUS_TEXT_LIMIT", 32768)

# # -----------------------------------------------------------------------------
# # Milvus
# # -----------------------------------------------------------------------------

# MILVUS_HOST = _required_env("MILVUS_HOST")
# MILVUS_PORT = _int_env("MILVUS_PORT", 19530)
# MILVUS_COLLECTION = _required_env("MILVUS_COLLECTION")
# MILVUS_DIMENSION = _int_env("MILVUS_DIMENSION", EMBEDDING_DIMENSION)

# MILVUS_INDEX_TYPE = _optional_env("MILVUS_INDEX_TYPE", "HNSW")
# MILVUS_METRIC_TYPE = _optional_env("MILVUS_METRIC_TYPE", "COSINE")
# MILVUS_NLIST = _int_env("MILVUS_NLIST", 1536)

# MILVUS_INSERT_BATCH = _int_env("MILVUS_INSERT_BATCH", 500)
# MILVUS_INSERT_SLEEP = _float_env("MILVUS_INSERT_SLEEP", 0.0)
# MILVUS_CONNECT_TIMEOUT = _int_env("MILVUS_CONNECT_TIMEOUT", 90)
# MILVUS_FLUSH_EVERY = _int_env("MILVUS_FLUSH_EVERY", 5000)

# MILVUS_CPU_WARN_THRESHOLD = _int_env("MILVUS_CPU_WARN_THRESHOLD", 65)
# MILVUS_CPU_PAUSE_THRESHOLD = _int_env("MILVUS_CPU_PAUSE_THRESHOLD", 70)
# MILVUS_CPU_MAX_WAIT = _int_env("MILVUS_CPU_MAX_WAIT", 60)
# MILVUS_MEM_WARN_THRESHOLD = _int_env("MILVUS_MEM_WARN_THRESHOLD", 80)
# MILVUS_LOG_PAYLOAD = _optional_env("MILVUS_LOG_PAYLOAD", "true").lower() == "true"

# # -----------------------------------------------------------------------------
# # Embedder CPU thresholds
# # -----------------------------------------------------------------------------

# EMBED_CPU_PAUSE_THRESHOLD = _int_env("EMBED_CPU_PAUSE_THRESHOLD", 70)
# EMBED_CPU_PAUSE_SECS = _float_env("EMBED_CPU_PAUSE_SECS", 3.0)

# # -----------------------------------------------------------------------------
# # Pipeline CPU thresholds
# # -----------------------------------------------------------------------------

# PIPELINE_CPU_WARN = _int_env("PIPELINE_CPU_WARN", 65)
# PIPELINE_CPU_PAUSE = _int_env("PIPELINE_CPU_PAUSE", 75)
# PIPELINE_CPU_MAX = _int_env("PIPELINE_CPU_MAX", 85)
# PIPELINE_DOC_SLEEP = _float_env("PIPELINE_DOC_SLEEP", 0.3)

# # -----------------------------------------------------------------------------
# # Optional legacy settings
# # -----------------------------------------------------------------------------

# LOVDATA_API_URL = _optional_env("LOVDATA_API_URL", "")
# LOVDATA_GET_ENDPOINT = _optional_env("LOVDATA_GET_ENDPOINT", "/get")
# XML_PROCESS_WORKERS = _int_env("XML_PROCESS_WORKERS", 2)

# SCHEDULER_BATCH_SIZE = _int_env("SCHEDULER_BATCH_SIZE", 50)
# SCHEDULER_CRON_HOUR = _int_env("SCHEDULER_CRON_HOUR", 2)
# SCHEDULER_CRON_MINUTE = _int_env("SCHEDULER_CRON_MINUTE", 0)
# SCHEDULER_API_TIMEOUT = _int_env("SCHEDULER_API_TIMEOUT", 30)
# MAX_WORKERS = 4

# # -----------------------------------------------------------------------------
# # XAPI Settings
# # -----------------------------------------------------------------------------

# XAPI_BASE_URL = _optional_env("XAPI_BASE_URL", "")
# XAPI_KEY = _optional_env("XAPI_KEY", "")
# XAPI_NAME = _optional_env("XAPI_NAME", "XAPI_SOURCE")
# XAPI_FETCH_LIMIT = _int_env("XAPI_FETCH_LIMIT", 50)
# # -----------------------------------------------------------------------------
# # Validation
# # -----------------------------------------------------------------------------

# def validate_runtime_config() -> None:
#     if not XL_DATASET_FOLDER.exists():
#         raise RuntimeError(
#             f"XL_DATASET_FOLDER path does not exist → {XL_DATASET_FOLDER}"
#         )

#     required_values = {
#         "SUPABASE_URL": SUPABASE_URL,
#         "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY,
#         "SUPABASE_BUCKET": SUPABASE_BUCKET,
#         "SUPABASE_TABLE": SUPABASE_TABLE,
#         "SUPABASE_SOURCE_TABLE_AI": SUPABASE_SOURCE_TABLE_AI,
#         "SUPABASE_SOURCE_TABLE_PREDEFINED": SUPABASE_SOURCE_TABLE_PREDEFINED,
#         "MILVUS_HOST": MILVUS_HOST,
#         "MILVUS_COLLECTION": MILVUS_COLLECTION,
#         "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
#         "AZURE_OPENAI_KEY": AZURE_OPENAI_KEY,
#         "AZURE_OPENAI_API_VERSION": AZURE_OPENAI_API_VERSION,
#         "AZURE_OPENAI_DEPLOYMENT": AZURE_OPENAI_DEPLOYMENT,
#     }

#     missing = [key for key, value in required_values.items() if not str(value).strip()]
#     if missing:
#         raise RuntimeError(f"Missing required config values: {', '.join(missing)}")

# # -----------------------------------------------------------------------------
# # Logging
# # -----------------------------------------------------------------------------

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s | %(levelname)s | %(message)s",
#     handlers=[
#         logging.FileHandler(LOG_FILE, encoding="utf-8"),
#         logging.StreamHandler(),
#     ],
#     force=True,
# )

# logger = logging.getLogger("digirett-ingestion")

# if __name__ == "__main__":
#     validate_runtime_config()
#     logger.info("✅ Configuration loaded successfully")
#     logger.info("Workbook folder → %s", XL_DATASET_FOLDER)
#     logger.info("Supabase bucket → %s", SUPABASE_BUCKET)
#     logger.info("Milvus → %s:%s | collection=%s", MILVUS_HOST, MILVUS_PORT, MILVUS_COLLECTION)

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Load environment
# -----------------------------------------------------------------------------

load_dotenv()


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} missing")
    return value


def _optional_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name, str(default)).strip()
    return int(value)


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name, str(default)).strip()
    return float(value)


# -----------------------------------------------------------------------------
# Base directories
# -----------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"
CLEAN_TEXT_DIR = DATA_DIR / "cleaned_text"
RAW_XML_DIR = DATA_DIR / "raw_xml"
ARCHIVE_DIR = DATA_DIR / "archives"

for folder in [DATA_DIR, LOG_DIR, CHECKPOINT_DIR, CLEAN_TEXT_DIR, RAW_XML_DIR, ARCHIVE_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "ingestion.log"

# -----------------------------------------------------------------------------
# Workbook / input
# -----------------------------------------------------------------------------

XL_DATASET_FOLDER = Path(_required_env("XL_DATASET_FOLDER"))

# -----------------------------------------------------------------------------
# Supabase — existing pipeline (DO NOT CHANGE THESE)
# -----------------------------------------------------------------------------

SUPABASE_URL = _required_env("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _required_env("SUPABASE_SERVICE_KEY")

# Old XML bucket — existing flow
SUPABASE_BUCKET = _required_env("SUPABASE_BUCKET")

# Final output metadata table — existing flow
SUPABASE_TABLE = _required_env("SUPABASE_TABLE")

# Source lookup tables — existing flow
SUPABASE_SOURCE_TABLE_AI = _required_env("SUPABASE_SOURCE_TABLE_AI")
SUPABASE_SOURCE_TABLE_PREDEFINED = _required_env("SUPABASE_SOURCE_TABLE_PREDEFINED")

# Raw ingestion metadata table — existing flow
SUPABASE_RAW_METADATA_TABLE = _optional_env("SUPABASE_RAW_METADATA_TABLE", "raw_ingestion_metadata")

# -----------------------------------------------------------------------------
# Supabase — XAPI new flow (NEW)
# Bucket for JSON files: raw_json_files
# Metadata table:        xapi_lovdata_metadata
# -----------------------------------------------------------------------------

SUPABASE_XAPI_BUCKET = _optional_env("SUPABASE_XAPI_BUCKET", "raw_json_files")
SUPABASE_XAPI_TABLE = _optional_env("SUPABASE_XAPI_TABLE", "xapi_lovdata_metadata")

# -----------------------------------------------------------------------------
# Azure OpenAI / embeddings
# -----------------------------------------------------------------------------

EMBEDDING_PROVIDER = _optional_env("EMBEDDING_PROVIDER", "azure_openai")
EMBEDDING_MODEL = _optional_env("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSION = _int_env("EMBEDDING_DIMENSION", 1536)

AZURE_OPENAI_ENDPOINT = _required_env("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = _required_env("AZURE_OPENAI_KEY")
AZURE_OPENAI_API_VERSION = _required_env("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT = _required_env("AZURE_OPENAI_DEPLOYMENT")

EMBEDDING_BATCH_SIZE = _int_env("EMBEDDING_BATCH_SIZE", 4)
EMBEDDING_CHUNK_DELAY = _float_env("EMBEDDING_CHUNK_DELAY", 0.5)

# -----------------------------------------------------------------------------
# Chunking
# -----------------------------------------------------------------------------

MAX_TOKENS_PER_CHUNK = _int_env("MAX_TOKENS_PER_CHUNK", 512)
OVERLAP_TOKENS = _int_env("OVERLAP_TOKENS", 50)
CHUNK_SIZE = _int_env("CHUNK_SIZE", 1000)
CHUNK_OVERLAP = _int_env("CHUNK_OVERLAP", 200)

# New section-aware chunker settings
MAX_CHUNK_SIZE_CHARS = _int_env("MAX_CHUNK_SIZE_CHARS", 12000)
MILVUS_TEXT_LIMIT = _int_env("MILVUS_TEXT_LIMIT", 32768)

# -----------------------------------------------------------------------------
# Milvus
# -----------------------------------------------------------------------------

MILVUS_HOST = _required_env("MILVUS_HOST")
MILVUS_PORT = _int_env("MILVUS_PORT", 19530)
MILVUS_COLLECTION = _required_env("MILVUS_COLLECTION")
MILVUS_DIMENSION = _int_env("MILVUS_DIMENSION", EMBEDDING_DIMENSION)

MILVUS_INDEX_TYPE = _optional_env("MILVUS_INDEX_TYPE", "HNSW")
MILVUS_METRIC_TYPE = _optional_env("MILVUS_METRIC_TYPE", "COSINE")
MILVUS_NLIST = _int_env("MILVUS_NLIST", 1536)

MILVUS_INSERT_BATCH = _int_env("MILVUS_INSERT_BATCH", 500)
MILVUS_INSERT_SLEEP = _float_env("MILVUS_INSERT_SLEEP", 0.0)
MILVUS_CONNECT_TIMEOUT = _int_env("MILVUS_CONNECT_TIMEOUT", 90)
MILVUS_FLUSH_EVERY = _int_env("MILVUS_FLUSH_EVERY", 5000)

MILVUS_CPU_WARN_THRESHOLD = _int_env("MILVUS_CPU_WARN_THRESHOLD", 65)
MILVUS_CPU_PAUSE_THRESHOLD = _int_env("MILVUS_CPU_PAUSE_THRESHOLD", 70)
MILVUS_CPU_MAX_WAIT = _int_env("MILVUS_CPU_MAX_WAIT", 60)
MILVUS_MEM_WARN_THRESHOLD = _int_env("MILVUS_MEM_WARN_THRESHOLD", 80)
MILVUS_LOG_PAYLOAD = _optional_env("MILVUS_LOG_PAYLOAD", "true").lower() == "true"

# -----------------------------------------------------------------------------
# Embedder CPU thresholds
# -----------------------------------------------------------------------------

EMBED_CPU_PAUSE_THRESHOLD = _int_env("EMBED_CPU_PAUSE_THRESHOLD", 70)
EMBED_CPU_PAUSE_SECS = _float_env("EMBED_CPU_PAUSE_SECS", 3.0)

# -----------------------------------------------------------------------------
# Pipeline CPU thresholds
# -----------------------------------------------------------------------------

PIPELINE_CPU_WARN = _int_env("PIPELINE_CPU_WARN", 65)
PIPELINE_CPU_PAUSE = _int_env("PIPELINE_CPU_PAUSE", 75)
PIPELINE_CPU_MAX = _int_env("PIPELINE_CPU_MAX", 85)
PIPELINE_DOC_SLEEP = _float_env("PIPELINE_DOC_SLEEP", 0.3)

# -----------------------------------------------------------------------------
# Optional legacy settings
# -----------------------------------------------------------------------------

LOVDATA_API_URL = _optional_env("LOVDATA_API_URL", "")
LOVDATA_GET_ENDPOINT = _optional_env("LOVDATA_GET_ENDPOINT", "/get")
XML_PROCESS_WORKERS = _int_env("XML_PROCESS_WORKERS", 2)

SCHEDULER_BATCH_SIZE = _int_env("SCHEDULER_BATCH_SIZE", 50)
SCHEDULER_CRON_HOUR = _int_env("SCHEDULER_CRON_HOUR", 2)
SCHEDULER_CRON_MINUTE = _int_env("SCHEDULER_CRON_MINUTE", 0)
SCHEDULER_API_TIMEOUT = _int_env("SCHEDULER_API_TIMEOUT", 30)
MAX_WORKERS = 4

# -----------------------------------------------------------------------------
# XAPI Settings
# Read from env only — no hardcoded keys.
# Used by xapi_lovdata_collector.py.
#
# XAPI_BASE_URL : https://xapi.no
# XAPI_KEY      : API key — sent as header X-API-Key (NOT Authorization Bearer)
# XAPI_NAME     : internal label for this source
# XAPI_FETCH_LIMIT : legacy fetch limit
# -----------------------------------------------------------------------------

XAPI_BASE_URL = _optional_env("XAPI_BASE_URL", "https://xapi.no")
XAPI_KEY = _optional_env("XAPI_KEY", "")
XAPI_NAME = _optional_env("XAPI_NAME", "XAPI_SOURCE_V1")
XAPI_FETCH_LIMIT = _int_env("XAPI_FETCH_LIMIT", 50)

# -----------------------------------------------------------------------------
# Validation — only called by the existing Excel/XML pipeline (main.py)
# NOT called by xapi_lovdata_collector.py — that script validates its own env.
# -----------------------------------------------------------------------------


def validate_runtime_config() -> None:
    if not XL_DATASET_FOLDER.exists():
        raise RuntimeError(
            f"XL_DATASET_FOLDER path does not exist → {XL_DATASET_FOLDER}"
        )

    required_values = {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY,
        "SUPABASE_BUCKET": SUPABASE_BUCKET,
        "SUPABASE_TABLE": SUPABASE_TABLE,
        "SUPABASE_SOURCE_TABLE_AI": SUPABASE_SOURCE_TABLE_AI,
        "SUPABASE_SOURCE_TABLE_PREDEFINED": SUPABASE_SOURCE_TABLE_PREDEFINED,
        "MILVUS_HOST": MILVUS_HOST,
        "MILVUS_COLLECTION": MILVUS_COLLECTION,
        "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
        "AZURE_OPENAI_KEY": AZURE_OPENAI_KEY,
        "AZURE_OPENAI_API_VERSION": AZURE_OPENAI_API_VERSION,
        "AZURE_OPENAI_DEPLOYMENT": AZURE_OPENAI_DEPLOYMENT,
    }

    missing = [key for key, value in required_values.items() if not str(value).strip()]
    if missing:
        raise RuntimeError(f"Missing required config values: {', '.join(missing)}")


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
    force=True,
)

logger = logging.getLogger("digirett-ingestion")

if __name__ == "__main__":
    validate_runtime_config()
    logger.info("✅ Configuration loaded successfully")
    logger.info("Workbook folder → %s", XL_DATASET_FOLDER)
    logger.info("Supabase bucket (XML) → %s", SUPABASE_BUCKET)
    logger.info("Supabase bucket (XAPI JSON) → %s", SUPABASE_XAPI_BUCKET)
    logger.info("XAPI metadata table → %s", SUPABASE_XAPI_TABLE)
    logger.info("Milvus → %s:%s | collection=%s", MILVUS_HOST, MILVUS_PORT, MILVUS_COLLECTION)

XAPI_REQUEST_DELAY_SECONDS = float(os.getenv("XAPI_REQUEST_DELAY_SECONDS", "1.5"))
XAPI_RETRY_MAX_ATTEMPTS = int(os.getenv("XAPI_RETRY_MAX_ATTEMPTS", "5"))
XAPI_RETRY_BASE_SECONDS = float(os.getenv("XAPI_RETRY_BASE_SECONDS", "3"))