from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base Directory Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"
NORMALIZED_DIR = DATA_DIR / "normalized"
REPORTS_DIR = BASE_DIR / "reports"

for folder in [DATA_DIR, LOG_DIR, CHECKPOINT_DIR, NORMALIZED_DIR, REPORTS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "ingestion.log"


class Settings(BaseSettings):
    """Runtime configuration for DigiRett Legal Ingestion Pipeline.
    
    Acts as the Single Configuration Interface (SSOT). All environment variables
    from .env are automatically loaded, validated, and typed by Pydantic.
    """

    # ── XAPI Connection & Auth ───────────────────────────────────────────
    XAPI_BASE_URL: str = "https://xapi.no"
    XAPI_API_KEY: str = ""
    XAPI_BEARER_TOKEN: str = ""
    XAPI_API_KEY_HEADER: str = "x-api-key"

    # ── XAPI Pacing & Concurrency ────────────────────────────────────────
    XAPI_LIMIT: int = 2500
    XAPI_TIMEOUT_SECONDS: float = 120.0
    XAPI_MAX_RETRIES: int = 4
    XAPI_CONCURRENCY: int = 8
    XAPI_BACKOFF_SECONDS: float = 2.0
    XAPI_REQUEST_PACING_SECONDS: float = 0.02

    # ── Supabase PostgreSQL & Storage ────────────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_BUCKET: str = "raw_json_files"

    # ── Document Batching ────────────────────────────────────────────────
    DOCUMENT_BATCH_SIZE: int = 50

    # ── Milvus Vector Database ───────────────────────────────────────────
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "digirett_xapi_data"
    MILVUS_BATCH_SIZE: int = 100
    MILVUS_MAX_RETRIES: int = 3
    MILVUS_DIMENSION: int = 1536
    MILVUS_METRIC_TYPE: str = "COSINE"
    MILVUS_INDEX_TYPE: str = "HNSW"

    # ── Azure OpenAI & AI Routing ────────────────────────────────────────
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_KEY: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = "text-embedding-3-small"
    AZURE_OPENAI_CHAT_DEPLOYMENT: str = "gpt-4o-mini"
    AZURE_OPENAI_API_VERSION: str = "2024-02-01"
    AI_ROUTING_ENABLED: bool = True
    AI_CONFIDENCE_THRESHOLD: float = 0.65
    AI_SCOPE_VALIDATION_ENABLED: bool = True

    # ── Embedding Model & Pacing ─────────────────────────────────────────
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_BATCH_SIZE: int = 64
    EMBEDDING_CHUNK_DELAY: float = 0.05

    # ── Legal Chunking Tokens ────────────────────────────────────────────
    LEGAL_CHUNK_MAX_TOKENS: int = 2000
    LEGAL_CHUNK_OVERLAP_TOKENS: int = 200
    LEGAL_CHUNK_CHARS_PER_TOKEN: int = 4

    # ── Scheduler ────────────────────────────────────────────────────────
    SCHEDULER_CRON_HOUR: int = 2
    SCHEDULER_CRON_MINUTE: int = 0
    SCHEDULER_API_TIMEOUT: int = 30

    # ── URL Validation Gate ──────────────────────────────────────────────
    URL_VALIDATION_ENABLED: bool = True
    URL_VALIDATION_CONCURRENCY: int = 5
    URL_VALIDATION_TIMEOUT: int = 15

    # ── Fixed xAPI Protocol Routes & Internal Constants ──────────────────
    XAPI_AREAS_PATH: str = "/v1/lovdata/rettsomrader"
    XAPI_LAWS_PATH: str = "/v1/lovdata/lover"
    XAPI_LAW_DETAIL_PATH: str = "/v1/lovdata/lover/{id}"
    XAPI_LAW_PARAGRAPHS_PATH: str = "/v1/lovdata/lover/{id}/paragrafer"
    XAPI_REGULATIONS_PATH: str = "/v1/lovdata/forskrifter"
    XAPI_LAW_REGULATIONS_PATH: str = "/v1/lovdata/forskrifter/{law_doc_id}"
    XAPI_LAW_AREA_PARAM: str = "rettsomrade"
    XAPI_REGULATION_AREA_PARAM: str = "rettsomrade"
    XAPI_LAW_TYPE: str = "lov"
    XAPI_CENTRAL_REGULATION_TYPE: str = "sentral"
    XAPI_INCLUDE_REGULATION_FULLTEXT: int = 1
    XAPI_INCLUDE_REMOVED_PARAGRAPHS: bool = False
    FILTER_LINKED_REGULATIONS_BY_DOMAIN: bool = False
    XAPI_MAX_PAGES: int = 1000
    LOVDATA_API_URL: str = "https://api.lovdata.no"
    LOVDATA_BASE_URL: str = "https://lovdata.no/dokument"
    SUPABASE_DB_URL: str = ""
    TAXONOMY_VERSION: str = "1.1.0"
    MILVUS_TEXT_LIMIT: int = 65000
    MAX_CHUNK_SIZE_CHARS: int = 2000
    EMBED_CPU_PAUSE_THRESHOLD: float = 70.0
    EMBED_CPU_PAUSE_SECS: float = 5.0
    EMBEDDING_MAX_RETRIES: int = 3
    EMBEDDING_RETRY_DELAY: int = 15
    MAPPING_PATH: Path = BASE_DIR / "configs" / "rettsomrade_domain_mapping.json"

    # ── Clean Pydantic Validators ────────────────────────────────────────
    @field_validator("XAPI_BASE_URL")
    @classmethod
    def clean_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("XAPI_LIMIT")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        if not 1 <= value <= 2500:
            raise ValueError("XAPI_LIMIT must be between 1 and 2500")
        return value

    # ── Backward-Compatibility Accessors (lowercase properties) ──────────
    @property
    def xapi_base_url(self) -> str:
        return self.XAPI_BASE_URL

    @property
    def xapi_bearer_token(self) -> str:
        return self.XAPI_BEARER_TOKEN

    @property
    def xapi_api_key(self) -> str:
        return self.XAPI_API_KEY

    @property
    def xapi_api_key_header(self) -> str:
        return self.XAPI_API_KEY_HEADER

    @property
    def xapi_limit(self) -> int:
        return self.XAPI_LIMIT

    @property
    def xapi_timeout_seconds(self) -> float:
        return self.XAPI_TIMEOUT_SECONDS

    @property
    def xapi_max_retries(self) -> int:
        return self.XAPI_MAX_RETRIES

    @property
    def xapi_concurrency(self) -> int:
        return self.XAPI_CONCURRENCY

    @property
    def xapi_backoff_seconds(self) -> float:
        return self.XAPI_BACKOFF_SECONDS

    @property
    def xapi_request_pacing_seconds(self) -> float:
        return self.XAPI_REQUEST_PACING_SECONDS

    @property
    def supabase_url(self) -> str:
        return self.SUPABASE_URL

    @property
    def supabase_service_key(self) -> str:
        return self.SUPABASE_SERVICE_ROLE_KEY or self.SUPABASE_KEY

    @property
    def supabase_bucket(self) -> str:
        return self.SUPABASE_BUCKET

    @property
    def document_batch_size(self) -> int:
        return self.DOCUMENT_BATCH_SIZE

    @property
    def milvus_host(self) -> str:
        return self.MILVUS_HOST

    @property
    def milvus_port(self) -> int:
        return self.MILVUS_PORT

    @property
    def milvus_collection(self) -> str:
        return self.MILVUS_COLLECTION

    @property
    def milvus_batch_size(self) -> int:
        return self.MILVUS_BATCH_SIZE

    @property
    def milvus_max_retries(self) -> int:
        return self.MILVUS_MAX_RETRIES

    @property
    def milvus_dimension(self) -> int:
        return self.MILVUS_DIMENSION

    @property
    def milvus_metric_type(self) -> str:
        return self.MILVUS_METRIC_TYPE

    @property
    def milvus_index_type(self) -> str:
        return self.MILVUS_INDEX_TYPE

    @property
    def azure_openai_endpoint(self) -> str:
        return self.AZURE_OPENAI_ENDPOINT

    @property
    def azure_openai_key(self) -> str:
        return self.AZURE_OPENAI_KEY

    @property
    def azure_openai_deployment(self) -> str:
        return self.AZURE_OPENAI_DEPLOYMENT

    @property
    def azure_openai_chat_deployment(self) -> str:
        return self.AZURE_OPENAI_CHAT_DEPLOYMENT

    @property
    def azure_openai_api_version(self) -> str:
        return self.AZURE_OPENAI_API_VERSION

    @property
    def ai_routing_enabled(self) -> bool:
        return self.AI_ROUTING_ENABLED

    @property
    def ai_confidence_threshold(self) -> float:
        return self.AI_CONFIDENCE_THRESHOLD

    @property
    def ai_scope_validation_enabled(self) -> bool:
        return self.AI_SCOPE_VALIDATION_ENABLED

    @property
    def embedding_model(self) -> str:
        return self.EMBEDDING_MODEL

    @property
    def embedding_batch_size(self) -> int:
        return self.EMBEDDING_BATCH_SIZE

    @property
    def embedding_chunk_delay(self) -> float:
        return self.EMBEDDING_CHUNK_DELAY

    @property
    def legal_chunk_max_tokens(self) -> int:
        return self.LEGAL_CHUNK_MAX_TOKENS

    @property
    def legal_chunk_overlap_tokens(self) -> int:
        return self.LEGAL_CHUNK_OVERLAP_TOKENS

    @property
    def legal_chunk_chars_per_token(self) -> int:
        return self.LEGAL_CHUNK_CHARS_PER_TOKEN

    @property
    def scheduler_cron_hour(self) -> int:
        return self.SCHEDULER_CRON_HOUR

    @property
    def scheduler_cron_minute(self) -> int:
        return self.SCHEDULER_CRON_MINUTE

    @property
    def scheduler_api_timeout(self) -> int:
        return self.SCHEDULER_API_TIMEOUT

    @property
    def url_validation_enabled(self) -> bool:
        return self.URL_VALIDATION_ENABLED

    @property
    def url_validation_concurrency(self) -> int:
        return self.URL_VALIDATION_CONCURRENCY

    @property
    def url_validation_timeout(self) -> int:
        return self.URL_VALIDATION_TIMEOUT

    @property
    def xapi_areas_path(self) -> str:
        return self.XAPI_AREAS_PATH

    @property
    def xapi_laws_path(self) -> str:
        return self.XAPI_LAWS_PATH

    @property
    def xapi_law_detail_path(self) -> str:
        return self.XAPI_LAW_DETAIL_PATH

    @property
    def xapi_law_paragraphs_path(self) -> str:
        return self.XAPI_LAW_PARAGRAPHS_PATH

    @property
    def xapi_regulations_path(self) -> str:
        return self.XAPI_REGULATIONS_PATH

    @property
    def xapi_law_regulations_path(self) -> str:
        return self.XAPI_LAW_REGULATIONS_PATH

    @property
    def xapi_law_area_param(self) -> str:
        return self.XAPI_LAW_AREA_PARAM

    @property
    def xapi_regulation_area_param(self) -> str:
        return self.XAPI_REGULATION_AREA_PARAM

    @property
    def xapi_law_type(self) -> str:
        return self.XAPI_LAW_TYPE

    @property
    def xapi_central_regulation_type(self) -> str:
        return self.XAPI_CENTRAL_REGULATION_TYPE

    @property
    def xapi_include_regulation_fulltext(self) -> int:
        return self.XAPI_INCLUDE_REGULATION_FULLTEXT

    @property
    def xapi_include_removed_paragraphs(self) -> bool:
        return self.XAPI_INCLUDE_REMOVED_PARAGRAPHS

    @property
    def filter_linked_regulations_by_domain(self) -> bool:
        return self.FILTER_LINKED_REGULATIONS_BY_DOMAIN

    @property
    def xapi_max_pages(self) -> int:
        return self.XAPI_MAX_PAGES

    @property
    def lovdata_api_url(self) -> str:
        return self.LOVDATA_API_URL

    @property
    def lovdata_base_url(self) -> str:
        return self.LOVDATA_BASE_URL

    @property
    def supabase_db_url(self) -> str:
        return self.SUPABASE_DB_URL

    @property
    def taxonomy_version(self) -> str:
        return self.TAXONOMY_VERSION

    @property
    def milvus_text_limit(self) -> int:
        return self.MILVUS_TEXT_LIMIT

    @property
    def max_chunk_size_chars(self) -> int:
        return self.MAX_CHUNK_SIZE_CHARS

    @property
    def embed_cpu_pause_threshold(self) -> float:
        return self.EMBED_CPU_PAUSE_THRESHOLD

    @property
    def embed_cpu_pause_secs(self) -> float:
        return self.EMBED_CPU_PAUSE_SECS

    @property
    def embedding_max_retries(self) -> int:
        return self.EMBEDDING_MAX_RETRIES

    @property
    def embedding_retry_delay(self) -> int:
        return self.EMBEDDING_RETRY_DELAY

    @property
    def mapping_path(self) -> Path:
        return self.MAPPING_PATH

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Single Global Settings Instance
settings = Settings()

# Consolidated Module-Level Backward-Compatible Aliases
XAPI_BASE_URL: str = settings.XAPI_BASE_URL
XAPI_API_KEY: str = settings.XAPI_API_KEY
XAPI_BEARER_TOKEN: str = settings.XAPI_BEARER_TOKEN
XAPI_API_KEY_HEADER: str = settings.XAPI_API_KEY_HEADER
XAPI_LIMIT: int = settings.XAPI_LIMIT
XAPI_TIMEOUT_SECONDS: float = settings.XAPI_TIMEOUT_SECONDS
XAPI_MAX_RETRIES: int = settings.XAPI_MAX_RETRIES
XAPI_CONCURRENCY: int = settings.XAPI_CONCURRENCY
XAPI_BACKOFF_SECONDS: float = settings.XAPI_BACKOFF_SECONDS
XAPI_REQUEST_PACING_SECONDS: float = settings.XAPI_REQUEST_PACING_SECONDS

SUPABASE_URL: str = settings.SUPABASE_URL
SUPABASE_KEY: str = settings.SUPABASE_KEY
SUPABASE_SERVICE_ROLE_KEY: Optional[str] = settings.SUPABASE_SERVICE_ROLE_KEY
SUPABASE_BUCKET: str = settings.SUPABASE_BUCKET
SUPABASE_DB_URL: str = settings.SUPABASE_DB_URL

LOVDATA_API_URL: str = settings.LOVDATA_API_URL
LOVDATA_BASE_URL: str = settings.LOVDATA_BASE_URL
MILVUS_COLLECTION: str = settings.MILVUS_COLLECTION
MILVUS_HOST: str = settings.MILVUS_HOST
MILVUS_PORT: int = settings.MILVUS_PORT
MILVUS_BATCH_SIZE: int = settings.MILVUS_BATCH_SIZE
MILVUS_MAX_RETRIES: int = settings.MILVUS_MAX_RETRIES
MILVUS_DIMENSION: int = settings.MILVUS_DIMENSION
MILVUS_METRIC_TYPE: str = settings.MILVUS_METRIC_TYPE
MILVUS_INDEX_TYPE: str = settings.MILVUS_INDEX_TYPE
MILVUS_TEXT_LIMIT: int = settings.MILVUS_TEXT_LIMIT

MAX_CHUNK_SIZE_CHARS: int = settings.MAX_CHUNK_SIZE_CHARS
LEGAL_CHUNK_MAX_TOKENS: int = settings.LEGAL_CHUNK_MAX_TOKENS
LEGAL_CHUNK_OVERLAP_TOKENS: int = settings.LEGAL_CHUNK_OVERLAP_TOKENS
LEGAL_CHUNK_CHARS_PER_TOKEN: int = settings.LEGAL_CHUNK_CHARS_PER_TOKEN

AZURE_OPENAI_ENDPOINT: str = settings.AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_KEY: str = settings.AZURE_OPENAI_KEY
AZURE_OPENAI_API_VERSION: str = settings.AZURE_OPENAI_API_VERSION
AZURE_OPENAI_DEPLOYMENT: str = settings.AZURE_OPENAI_DEPLOYMENT
AZURE_OPENAI_CHAT_DEPLOYMENT: str = settings.AZURE_OPENAI_CHAT_DEPLOYMENT
AI_ROUTING_ENABLED: bool = settings.AI_ROUTING_ENABLED
AI_CONFIDENCE_THRESHOLD: float = settings.AI_CONFIDENCE_THRESHOLD
AI_SCOPE_VALIDATION_ENABLED: bool = settings.AI_SCOPE_VALIDATION_ENABLED

EMBEDDING_MODEL: str = settings.EMBEDDING_MODEL
EMBED_CPU_PAUSE_THRESHOLD: float = settings.EMBED_CPU_PAUSE_THRESHOLD
EMBED_CPU_PAUSE_SECS: float = settings.EMBED_CPU_PAUSE_SECS
EMBEDDING_BATCH_SIZE: int = settings.EMBEDDING_BATCH_SIZE
EMBEDDING_CHUNK_DELAY: float = settings.EMBEDDING_CHUNK_DELAY
EMBEDDING_MAX_RETRIES: int = settings.EMBEDDING_MAX_RETRIES
EMBEDDING_RETRY_DELAY: int = settings.EMBEDDING_RETRY_DELAY

DOCUMENT_BATCH_SIZE: int = settings.DOCUMENT_BATCH_SIZE
INGESTION_BATCH_SIZE: int = settings.DOCUMENT_BATCH_SIZE

SCHEDULER_CRON_HOUR: int = settings.SCHEDULER_CRON_HOUR
SCHEDULER_CRON_MINUTE: int = settings.SCHEDULER_CRON_MINUTE
SCHEDULER_API_TIMEOUT: int = settings.SCHEDULER_API_TIMEOUT

URL_VALIDATION_ENABLED: bool = settings.URL_VALIDATION_ENABLED
URL_VALIDATION_CONCURRENCY: int = settings.URL_VALIDATION_CONCURRENCY
URL_VALIDATION_TIMEOUT: int = settings.URL_VALIDATION_TIMEOUT
TAXONOMY_VERSION: str = settings.TAXONOMY_VERSION
MAPPING_PATH: Path = settings.MAPPING_PATH

# Setup Dedicated Ingestion Logging
logger = logging.getLogger("digirett-ingestion")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    _file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    _file_handler.setFormatter(_formatter)
    _stream_handler = logging.StreamHandler()
    _stream_handler.setFormatter(_formatter)
    logger.addHandler(_file_handler)
    logger.addHandler(_stream_handler)