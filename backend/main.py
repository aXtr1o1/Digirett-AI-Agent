import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.routes import chat, conversations, health, messages
from config import settings
from db.milvus_client import get_milvus
from db.redis_client import get_redis
from db.supabase_client import get_supabase
from services.conversation_service import ConversationService
from services.embedding_service import EmbeddingService
from services.llm_service import LLMService
from services.message_service import MessageService
from services.rag_service import RAGService
from telemetry.tracing import setup_tracing
from utils.logger import setup_logger

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(asctime)s | %(name)s | %(message)s",
)
logger = setup_logger(__name__, level=settings.LOG_LEVEL)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting Lovdata RAG API...")

    milvus_client = None
    redis_client = None

    try:
        logger.info("Connecting to Milvus...")
        milvus_client = get_milvus()
        milvus_client.connect(
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
            collection_name=settings.MILVUS_COLLECTION,
        )

        logger.info("Connecting to Redis...")
        redis_client = get_redis()
        redis_client.connect(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
        )

        logger.info("Connecting to Supabase...")
        supabase_client = get_supabase()
        supabase_client.connect(
            url=settings.SUPABASE_URL,
            key=settings.SUPABASE_KEY,
        )

        logger.info("Initializing LLM service...")
        llm_service = LLMService(temperature=settings.OPENAI_TEMPERATURE)

        logger.info("Initializing Embedding service...")
        embedding_service = EmbeddingService()

        logger.info("Initializing RAG service...")
        rag_service = RAGService(
            llm_service=llm_service,
            milvus_client=milvus_client,
            redis_client=redis_client,
            supabase_client=supabase_client,
            embedding_service=embedding_service,
        )

        logger.info("Initializing Conversation service...")
        conversation_service = ConversationService(
            supabase_client=supabase_client,
            redis_client=redis_client,
        )

        logger.info("Initializing Message service...")
        message_service = MessageService(
            supabase_client=supabase_client,
            redis_client=redis_client,
        )

        logger.info("Injecting services into route modules...")

        health.set_clients(
            milvus=milvus_client,
            redis=redis_client,
            supabase=supabase_client,
            llm=llm_service,
        )
        chat.set_services(
            rag_service=rag_service,
            conversation_service=conversation_service,
            message_service=message_service,
            llm_service=llm_service,
        )
        conversations.set_services(
            conversation_service=conversation_service,
            message_service=message_service,
        )
        # CHANGED: pass conversation_service so messages route can do 404 checks
        messages.set_services(
            message_service=message_service,
            conversation_service=conversation_service,
        )

        logger.info("All services ready — server is live")

        yield

    except Exception as exc:
        logger.error(f"Startup failed | {exc}", exc_info=True)
        raise

    finally:
        logger.info("Shutting down...")

        if milvus_client:
            try:
                milvus_client.close()
            except Exception as exc:
                logger.error(f"Error closing Milvus: {exc}")

        if redis_client:
            try:
                redis_client.close()
            except Exception as exc:
                logger.error(f"Error closing Redis: {exc}")

        logger.info("Shutdown complete")


setup_tracing(service_name="lovdata-rag-api")

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "RAG system for Norwegian law — "
        "multi-turn conversations, agent-based routing, "
        "Redis caching, Supabase persistence."
    ),
    version=settings.VERSION,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router,        prefix="/api/v1")
app.include_router(chat.router,          prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(messages.router,      prefix="/api/v1")

logger.info("FastAPI app created")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )