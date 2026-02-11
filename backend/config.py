from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    # App
    APP_NAME: str
    VERSION: str
    DEBUG: bool
    ALLOWED_ORIGINS: List[str]

    # Logging
    LOG_DIR: str
    LOG_FILE: str
    LOG_LEVEL: str

    # Rate limit
    RATE_LIMIT_PER_MINUTE: int = 250

    # Milvus
    MILVUS_HOST: str
    MILVUS_PORT: int
    MILVUS_COLLECTION: str
    MILVUS_METRIC_TYPE: str

    # Embedding dimension
    EMBEDDING_DIMENSION: int

    # Redis
    REDIS_URL: str
    ENABLE_CACHE: bool = True
    CACHE_TTL: int

    # RAG Settings
    DEFAULT_TOP_K: int
    MAX_TOP_K: int
    MIN_SIMILARITY_SCORE: float
    CONTEXT_MAX_LENGTH: int

    # Azure OpenAI - CHAT
    AZURE_OPENAI_CHAT_ENDPOINT: str
    AZURE_OPENAI_CHAT_API_KEY: str
    AZURE_OPENAI_CHAT_API_VERSION: str
    AZURE_OPENAI_CHAT_DEPLOYMENT: str

    # Azure OpenAI - EMBEDDINGS
    AZURE_OPENAI_EMBED_ENDPOINT: str
    AZURE_OPENAI_EMBED_API_KEY: str
    AZURE_OPENAI_EMBED_API_VERSION: str
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str

    PROMPT_VERSION: str

    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
