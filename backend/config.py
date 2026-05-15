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

    # ── Reranker ─────────────────────────────────────────────────────────
    # Number of chunks to retrieve from Milvus before reranking (recall stage)
    RERANKER_RECALL_TOP_K: int
    # Number of chunks to keep after reranking (passed to validation + generation)
    RERANKER_FINAL_TOP_K: int
    RERANKER_MIN_SCORE: float

    # ── Rate Limiting ────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 250

    # ── Redis (deployed, not Docker) ─────────────────────────────────────
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_USERNAME: str | None = None
    REDIS_PASSWORD: str | None = None
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

    # ── Clerk Auth ────────────────────────────────────────────────────────
    # Secret key for Clerk SDK (update user metadata, admin API calls)
    CLERK_SECRET_KEY: str = ""
    # JWKS endpoint — verify Clerk JWTs (RS256 asymmetric signing)
    # Format: https://<clerk-instance>.clerk.accounts.dev/.well-known/jwks.json
    CLERK_JWKS_URL: str = ""
    # Svix webhook signing secret — from Clerk Dashboard → Webhooks
    # Required to validate incoming webhook payloads (prevents spoofing)
    CLERK_WEBHOOK_SECRET: str = ""
    # Default tenant UUID — the single tenant row in the tenants table.
    # Every new user is assigned this tenant on signup (webhook handler).
    DEFAULT_TENANT_ID: str = ""
    # ── SMTP (Phase 2 Migration from Resend) ──────────────────────────────
    SMTP_HOST: str = "smtp.resend.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "resend"
    SMTP_PASS: str = ""
    RESEND_API_KEY: Optional[str] = None
    # From-address for invitation emails
    INVITE_FROM_EMAIL: str = "sabari@axtr.in"
    # Frontend base URL — used to build the invite link in emails
    # Set to http://localhost:3000 in development, https://digirett.no in production
    FRONTEND_URL: str = "http://localhost:3000"

    # ── Conversation ─────────────────────────────────────────────────────
    AUTO_SUMMARY_THRESHOLD: int = 50
    DEFAULT_USER_ID: str = "2a06144d-4675-4c38-b7f8-13c02da91af5"
    MAX_CONVERSATION_TITLE_LENGTH: int = 100
    SOFT_DELETE: bool = True

    # ── Document Agent Session Limits ─────────────────────────────────────
    # Full session TTL — 4 hours. Redis keys for doc sessions expire after this.
    DOC_SESSION_TTL_SECONDS: int = 14400
    
    # ┌─━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┐
    # │ TESTING MODE — Commented out for document feature testing       │
    # │ Set DOC_TESTING_MODE = False to revert to production limits     │
    # └─━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┘
    DOC_TESTING_MODE: bool = True
    
    # Max documents a user can upload within one 4-hour session.
    # PRODUCTION: 2 | TESTING: 999 (unlimited for testing)
    DOC_MAX_PER_SESSION: int = 999 if DOC_TESTING_MODE else 2
    
    # Max query turns (user messages) allowed within one 4-hour session.
    # PRODUCTION: 10 | TESTING: 999 (unlimited for testing)
    DOC_MAX_TURNS_PER_SESSION: int = 999 if DOC_TESTING_MODE else 10
    
    # Max file size for document uploads (bytes). Default = 20 MB.
    DOC_MAX_FILE_SIZE_BYTES: int = 20 * 1024 * 1024

    # ── Logging ───────────────────────────────────────────────────────────
    # DEBUG level for detailed workflow visibility, INFO for production
    LOG_LEVEL: str = "DEBUG" if DOC_TESTING_MODE else "INFO"
    LOG_DIR: str = "./logs"
    LOG_WITH_COLORS: bool = True
    LOG_INCLUDE_TIMESTAMPS: bool = True
    LOG_INCLUDE_EMOJIS: bool = True
    
    # ── Query Enrichment (Phase 2) ────────────────────────────────────────
    ENABLE_ENRICHED_QUERY: bool = True
    ENRICHMENT_SUMMARY_MAX_CHARS: int = 500
    ENRICHMENT_KEYWORDS_COUNT: int = 5

    # ── Retry ─────────────────────────────────────────────────────────────
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0

    # ── Cal.com Integration ────────────────────────────────────────────────
    # Shared webhook secret from Cal.com dashboard → Webhooks → Secret
    # Used to verify X-Cal-Signature-256 header on incoming booking events
    CAL_COM_WEBHOOK_SECRET: Optional[str] = None

    # ── Admin Notifications ───────────────────────────────────────────────────
    # Email to receive alerts about unassigned HITL tickets
    ADMIN_ALERT_EMAIL: Optional[str]


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
