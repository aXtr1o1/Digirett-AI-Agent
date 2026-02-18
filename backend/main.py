"""
Main Application Entry Point
Minimal FastAPI app with service initialization
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .config import settings
from .utils.logger import setup_logger
from .api import endpoints

# DB Clients
from .db.milvus_client import get_milvus
from .db.redis import get_redis
from .db.supabase import get_supabase

# Services
from .services.llm_service import LLMService
from .services.rag_service import RAGService
from .services.embedding_service import EmbeddingService
from .services.conversation_service import ConversationService
from .services.message_service import MessageService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(asctime)s | %(name)s | %(message)s"
)
logger = setup_logger(__name__, level="INFO")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events
    Initialize all services with proper error handling
    """
    logger.info("🚀 Starting Lovdata RAG System with LangChain Agent...")
    
    # Service instances
    milvus_client = None
    redis_client = None
    supabase_client = None
    llm_service = None
    embedding_service = None
    rag_service = None
    conversation_service = None
    message_service = None
    
    try:
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: Initialize Database Clients
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        logger.info("🔌 Connecting to Milvus...")
        milvus_client = get_milvus()
        milvus_client.connect(
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
            collection_name=settings.MILVUS_COLLECTION
        )
        
        logger.info("🔌 Connecting to Redis...")
        redis_client = get_redis()
        redis_client.connect(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None
        )
        
        logger.info("🔌 Connecting to Supabase...")
        supabase_client = get_supabase()
        supabase_client.connect(
            url=settings.SUPABASE_URL,
            key=settings.SUPABASE_KEY
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: Initialize Services
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        logger.info("🤖 Initializing LLM service (OpenAI)...")
        llm_service = LLMService(
            temperature=settings.OPENAI_TEMPERATURE
        )
        
        logger.info("🔢 Initializing Embedding service...")
        embedding_service = EmbeddingService()
        
        logger.info("🧠 Initializing RAG service...")
        rag_service = RAGService(
            llm_service=llm_service,
            milvus_client=milvus_client,
            redis_client=redis_client,
            supabase_client=supabase_client,
            embedding_service=embedding_service
        )
        
        logger.info("💬 Initializing Conversation service...")
        conversation_service = ConversationService(
            supabase_client=supabase_client,
            redis_client=redis_client
        )
        
        logger.info("📝 Initializing Message service...")
        message_service = MessageService(
            supabase_client=supabase_client,
            redis_client=redis_client
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: Inject services into endpoints
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        logger.info("💉 Injecting services into endpoints...")
        endpoints.set_services(
            rag=rag_service,
            conv=conversation_service,
            msg=message_service,
            milvus=milvus_client,
            redis=redis_client,
            supabase=supabase_client,
            llm=llm_service,
        )
        
        logger.info("✅ All services initialized successfully!")
        
        yield
        
    except Exception as e:
        logger.error(
            f"❌ Failed to initialize services | "
            f"Error: {type(e).__name__}: {str(e)}",
            exc_info=True
        )
        raise
    
    finally:
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # SHUTDOWN: Clean up resources
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        logger.info("🛑 Shutting down services...")
        
        try:
            if milvus_client:
                milvus_client.close()
                logger.info("✅ Milvus connection closed")
        except Exception as e:
            logger.error(f"❌ Error closing Milvus: {e}")
        
        try:
            if redis_client:
                redis_client.close()
                logger.info("✅ Redis connection closed")
        except Exception as e:
            logger.error(f"❌ Error closing Redis: {e}")
        
        logger.info("🛑 Shutdown complete")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CREATE FASTAPI APP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

app = FastAPI(
    title="Lovdata RAG API with LangChain Agent",
    description="RAG system with multi-turn conversations, agent-based routing, Redis caching, and Supabase persistence",
    version="2.0.0",
    lifespan=lifespan
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(endpoints.router, prefix="/api/v1")

logger.info("✅ FastAPI app created successfully")


if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting Uvicorn server...")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )