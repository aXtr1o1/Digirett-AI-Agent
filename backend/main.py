import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware

from langchain_openai import AzureChatOpenAI

from backend.config import settings
from backend.api.endpoints import router, limiter
from backend.db.milvus_client import MilvusClient
from backend.db.redis import RedisCache
from backend.services.chat_service import ChatService
from backend.services.rag.retriever import MilvusRetriever
from backend.services.rag.generator import EmbeddingGenerator


def setup_logging():
    Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
    log_path = str(Path(settings.LOG_DIR) / settings.LOG_FILE)

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="[%(levelname)s] %(name)s - %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )


setup_logging()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, version=settings.VERSION)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # SlowAPI must be middleware to enforce limits
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Milvus
    milvus = MilvusClient(settings.MILVUS_HOST, settings.MILVUS_PORT, settings.MILVUS_COLLECTION)
    milvus.connect()

    # Redis
    cache = RedisCache(settings.REDIS_URL)

    # Azure OpenAI - Chat LLM
    llm = AzureChatOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_CHAT_ENDPOINT,
        api_key=settings.AZURE_OPENAI_CHAT_API_KEY,
        api_version=settings.AZURE_OPENAI_CHAT_API_VERSION,
        azure_deployment=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
        temperature=0.5,
    )

    # Embeddings
    embedder = EmbeddingGenerator()

    # Retriever
    retriever = MilvusRetriever(milvus.get_collection(), metric_type=settings.MILVUS_METRIC_TYPE)

    # Chat Service
    chat_service = ChatService(llm=llm, max_context_chars=settings.CONTEXT_MAX_LENGTH)

    # attach
    app.state.milvus = milvus
    app.state.cache = cache
    app.state.embedder = embedder
    app.state.retriever = retriever
    app.state.chat_service = chat_service

    # routes
    app.include_router(router)

    @app.on_event("shutdown")
    async def shutdown_event():
        try:
            if hasattr(app.state, "embedder"):
                await app.state.embedder.aclose()
        except Exception:
            pass
        try:
            if hasattr(app.state, "milvus"):
                app.state.milvus.close()
        except Exception:
            pass
        try:
            if hasattr(app.state, "cache"):
                app.state.cache.close()
        except Exception:
            pass

    logger.info("Backend started")
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
