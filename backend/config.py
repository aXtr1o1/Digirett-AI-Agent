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
    ALLOWED_ORIGINS: List[str] 

    # ========================
    # Milvus Settings
    # ========================
    MILVUS_HOST: str
    MILVUS_PORT: int
    MILVUS_COLLECTION: str
    MILVUS_METRIC_TYPE: str = "IP"
    MILVUS_INDEX_TYPE: str = "HNSW"
    DIMENSION: int


    AZURE_OPENAI_ENDPOINT: str
    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_DEPLOYMENT: str
    AZURE_OPENAI_API_VERSION: str
    OPENAI_TEMPERATURE: float
    
    # Embeddings
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str
    AZURE_OPENAI_EMBEDDING_API_VERSION: str
    # # ========================
    # # AWS Credentials
    # # ========================
    # AWS_ACCESS_KEY_ID: Optional[str] = None
    # AWS_SECRET_ACCESS_KEY: Optional[str] = None
    # AWS_DEFAULT_REGION: str = "ap-south-1"

    # ========================
    # RAG Settings
    # ========================
    DEFAULT_TOP_K: int 
    MAX_TOP_K: int
    MIN_SIMILARITY_SCORE: float 
    CONTEXT_MAX_LENGTH: int 

    # ========================
    # Rate Limiting
    # ========================
    RATE_LIMIT_PER_MINUTE: int = 250

    # ========================
    # Redis - Basic Cache
    # ========================
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int 
    REDIS_PASSWORD: str
    REDIS_SSL: bool = False   # 🔥 ADD THIS
    CACHE_TTL: int = 3600
    ENABLE_CACHE: bool = True
    
    # ========================
    # Redis - Conversation Memory (NEW)
    # ========================
    CONVERSATION_CONTEXT_TTL: int = 1800  # 30 minutes (sliding window)
    USER_SESSION_TTL: int = 3600  # 1 hour
    STREAMING_BUFFER_TTL: int = 60  # 1 minute
    MAX_CONTEXT_MESSAGES: int = 20  # Last N messages in context window
    CONVERSATION_META_TTL: int = 3600  # 1 hour for conversation metadata
    USER_CONVERSATIONS_TTL: int = 1800  # 30 minutes for user's conversation list
    
    # ========================
    # Supabase (NEW)
    # ========================
    SUPABASE_URL: str
    SUPABASE_KEY: str  # anon/public key
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None  # For admin operations
    
    # ========================
    # Conversation Settings (NEW)
    # ========================
    AUTO_SUMMARY_THRESHOLD: int = 50  # Auto-summarize after N messages
    DEFAULT_USER_ID: str = "admin"  # For MVP hardcoded users
    MAX_CONVERSATION_TITLE_LENGTH: int = 100
    SOFT_DELETE: bool = True  # Use soft delete for conversations/messages

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

    # ✅ Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()