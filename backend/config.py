"""
app/config.py
Configuration management using Pydantic v2
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List, Optional


class Settings(BaseSettings):
    """Application settings"""

    # ========================
    # API Settings
    # ========================
    APP_NAME: str = "Lovdata RAG API"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # ========================
    # Milvus Settings
    # ========================
    MILVUS_HOST: str
    MILVUS_PORT: int
    MILVUS_COLLECTION: str
    MILVUS_METRIC_TYPE: str = "IP"
    MILVUS_INDEX_TYPE: str = "HNSW"
    DIMENSION: int = 1024

    # ========================
    # LLM Provider
    # ========================
    LLM_PROVIDER: str = "fireworks"

    # ========================
    # AWS Credentials
    # ========================
    AWS_ACCESS_KEY_ID: Optional[str]
    AWS_SECRET_ACCESS_KEY: Optional[str]
    AWS_DEFAULT_REGION: str = "ap-south-1"

    # ========================
    # SageMaker
    # ========================
    SAGEMAKER_EMBEDDING_ENDPOINT: str
    MIN_SIMILARITY_SCORE: float


    # ========================
    # Fireworks.ai
    # ========================
    FIREWORKS_API_KEY: str
    FIREWORKS_MODEL: str

    # Azure

    Model_Name: str
    Target_URI: str
    Key: str
    API_Routes: str ="https://Llama-3-3-70B-Instruct-ejght.eastus2.models.ai.azure.com/v1/chat/completions"

    # ========================
    # Embedding
    # ========================
    EMBEDDING_MODEL: str = "BAAI/bge-m3"

    # ========================
    # RAG Settings
    # ========================
    DEFAULT_TOP_K: int = 3
    MAX_TOP_K: int = 10
    MIN_SIMILARITY_SCORE: float = 0.0
    CONTEXT_MAX_LENGTH: int = 32000

    # ========================
    # Rate Limiting
    # ========================
    RATE_LIMIT_PER_MINUTE: int = 250

    # ========================
    # Redis
    # ========================
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    CACHE_TTL: int = 3600
    ENABLE_CACHE: bool = True

    # ========================
    # Logging & Monitoring
    # ========================
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"
    ENABLE_METRICS: bool = True
    METRICS_PORT: int = 9090

    # ========================
    # Retry Logic
    # ========================
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0

    # ✅ THIS IS THE FIX (Pydantic v2)
    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"   # 🔥 VERY IMPORTANT
    )


settings = Settings()
