import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ── API ──────────────────────────────────────────────────────────────
    APP_NAME: str = "Lovdata RAG API"
    VERSION: str = "2.0.0"
    DEBUG: bool = False
    ALLOWED_ORIGINS: List[str]

    # ── Azure OpenAI ─────────────────────────────────────────────────────
    AZURE_OPENAI_ENDPOINT: str
    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_DEPLOYMENT: str
    AZURE_OPENAI_API_VERSION: str
    OPENAI_TEMPERATURE: float = 0.4

    # Embedding model (text-embedding-3-small)
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str
    AZURE_OPENAI_EMBEDDING_API_VERSION: str

    # ── Milvus ───────────────────────────────────────────────────────────
    MILVUS_HOST: str
    MILVUS_PORT: int
    MILVUS_COLLECTION: str
    MILVUS_METRIC_TYPE: str
    MILVUS_INDEX_TYPE: str
    DIMENSION: int = 1536

    # ── RAG ──────────────────────────────────────────────────────────────
    DEFAULT_TOP_K: int = 5
    MAX_TOP_K: int = 10
    MIN_SIMILARITY_SCORE: float = 0.8
    # Max characters of context sent to LLM (covers ~20 000 tokens)
    CONTEXT_MAX_LENGTH: int = 80000

    # ── Rate Limiting ────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 250

    # ── Redis (deployed, not Docker) ─────────────────────────────────────
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int
    REDIS_PASSWORD: str
    # TTLs (seconds)
    CACHE_TTL: int = 3600
    ENABLE_CACHE: bool = True
    CONVERSATION_CONTEXT_TTL: int = 1800 
    USER_SESSION_TTL: int = 3600
    STREAMING_BUFFER_TTL: int = 60
    MAX_CONTEXT_MESSAGES: int = 20
    CONVERSATION_META_TTL: int = 3600
    USER_CONVERSATIONS_TTL: int = 1800

    # ── Supabase ─────────────────────────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None

    # ── Conversation ──────────────────────────────────────────────────────
    AUTO_SUMMARY_THRESHOLD: int = 50
    DEFAULT_USER_ID: str = "admin"
    MAX_CONVERSATION_TITLE_LENGTH: int = 100
    SOFT_DELETE: bool = True

    # ── Logging ───────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"

    # ── Retry ─────────────────────────────────────────────────────────────
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()