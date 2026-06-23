import asyncio
import logging
from contextlib import asynccontextmanager

import secrets
from fastapi import FastAPI, Depends, Request, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.routes import admin, auth, chat, conversations, documents, health, hitl, invite, messages, webhooks
from api.routes import cal as cal_routes
from api.routes import cal_webhooks, notes
from config import settings
from db.milvus_client import get_milvus
from db.redis_client import get_redis
from db.supabase_client import get_supabase
from services.cal_service import CalService
from services.conversation_service import ConversationService
from services.document_service import DocumentService
from services.embedding_service import EmbeddingService
from services.email_service import EmailService
from services.hitl_service import HitlService
from services.llm_service import LLMService
from services.lovdata_title_fetcher import LovdataTitleFetcher
from services.message_service import MessageService
from services.rag_service import RAGService
from services.user_service import UserService
from services.notes_service import NotesService
from config import settings
from db.milvus_client import get_milvus
from db.redis_client import get_redis
from db.supabase_client import get_supabase
from telemetry.tracing import setup_tracing
from utils.logger import setup_logger

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(asctime)s | %(name)s | %(message)s",
)
logger = setup_logger(__name__, level=settings.LOG_LEVEL)

def get_rate_limit_key(request: Request) -> str:
    """Rate limit by Clerk user ID if available, otherwise fallback to IP."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            from jose import jwt
            unverified_claims = jwt.get_unverified_claims(token)
            clerk_id = unverified_claims.get("sub")
            if clerk_id:
                return clerk_id
        except Exception:
            pass
    return get_remote_address(request)

limiter = Limiter(key_func=get_rate_limit_key)


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting Lovdata RAG API...")

    milvus_client = None
    redis_client  = None

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
            password=settings.REDIS_PASSWORD,
        )

        logger.info("Connecting to Supabase...")
        supabase_client = get_supabase()
        
        # Use SERVICE_ROLE_KEY if available (for backend God Mode), otherwise fallback to ANON_KEY
        sb_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
        supabase_client.connect(
            url=settings.SUPABASE_URL,
            key=sb_key,
        )

        logger.info("Initializing LLM service...")
        llm_service = LLMService(temperature=settings.OPENAI_TEMPERATURE)

        logger.info("Initializing Embedding service...")
        embedding_service = EmbeddingService()

        logger.info("Initializing Document service...")
        document_service = DocumentService(
            redis_client=redis_client,
            supabase_client=supabase_client,
        )

        logger.info("Initializing RAG service...")
        rag_service = RAGService(
            llm_service=llm_service,
            milvus_client=milvus_client,
            redis_client=redis_client,
            supabase_client=supabase_client,
            embedding_service=embedding_service,
            document_service=document_service,
        )

        logger.info("Initializing Conversation service...")
        conversation_service = ConversationService(
            supabase_client=supabase_client,
            redis_client=redis_client,
        )

        logger.info("Initializing User service...")
        user_service = UserService(
            supabase_client=supabase_client,
        )

        logger.info("Initializing Email service...")
        email_service = EmailService(
            smtp_host=settings.SMTP_HOST,
            smtp_port=settings.SMTP_PORT,
            smtp_user=settings.SMTP_USER,
            smtp_pass=settings.SMTP_PASS,
            from_email=settings.INVITE_FROM_EMAIL,
        )

        logger.info("Initializing HITL service...")
        hitl_service = HitlService(
            supabase_client=supabase_client,
        )

        logger.info("Initializing Cal.com service...")
        cal_service = CalService()

        logger.info("Initializing Notes service...")
        notes_service = NotesService(supabase_client=supabase_client)

        # ── Title fetcher must be created BEFORE MessageService ──────────
        # It resolves Lovdata URLs to human-readable Norwegian titles using
        # a 3-layer cache: Redis (L1) → Supabase lovdata_url_titles (L2)
        # → httpx fetch (L3). MessageService calls it inside save_exchange.
        logger.info("Initializing Lovdata title fetcher...")
        title_fetcher = LovdataTitleFetcher(
            redis_client=redis_client,
            supabase_client=supabase_client,
        )

        logger.info("Initializing Message service...")
        message_service = MessageService(
            supabase_client=supabase_client,
            redis_client=redis_client,
            title_fetcher=title_fetcher,          # ← wired in
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
            document_service=document_service,  # ← added
            user_service=user_service,
        )
        conversations.set_services(
            conversation_service=conversation_service,
            message_service=message_service,
            user_service=user_service,
            hitl_service=hitl_service,
            document_service=document_service,
        )
        messages.set_services(
            message_service=message_service,
            conversation_service=conversation_service,
        )
        documents.set_services(
            document_service=document_service,
            llm_service=llm_service,
            user_service=user_service,
        )
        webhooks.set_services(
            user_service=user_service,
            email_service=email_service,
        )
        admin.set_services(
            user_svc=user_service,
            email_svc=email_service,
            hitl_svc=hitl_service,
        )
        hitl.set_services(
            hitl_svc=hitl_service,
            user_svc=user_service,
            email_svc=email_service,
        )
        cal_routes.set_services(
            cal_svc=cal_service,
            hitl_svc=hitl_service,
            user_svc=user_service,
        )
        cal_webhooks.set_services(
            hitl_svc=hitl_service,
            email_svc=email_service,
        )
        invite.set_services(
            supabase_client=supabase_client,
        )
        auth.set_services(
            user_service=user_service,
        )
        notes.set_services(
            notes_svc=notes_service,
            user_svc=user_service,
        )

        logger.info("All services ready — server is live")

        # ── 30-minute background alert task ──────────────────────────────────
        # Fires every 30 minutes. Finds open tickets older than 30 minutes
        # that haven't had an alert sent yet, emails admin, marks alert_sent_at.
        async def _unassigned_ticket_alert_task():
            INTERVAL_SECONDS = 30 * 60  # 30 minutes
            await asyncio.sleep(60)  # short initial delay to let startup finish
            while True:
                try:
                    admin_email = settings.ADMIN_ALERT_EMAIL
                    if not admin_email:
                        logger.debug("⏰ ADMIN_ALERT_EMAIL not set — skipping unassigned ticket check")
                    else:
                        stale = hitl_service.get_unassigned_tickets_older_than_minutes(minutes=30)
                        if stale:
                            logger.info(
                                f"⚠️ Background task: {len(stale)} unassigned tickets older than 30min — alerting admin"
                            )
                            await email_service.send_admin_unassigned_alert(
                                admin_email=admin_email,
                                unassigned_tickets=stale,
                            )
                            hitl_service.mark_alert_sent([t["ticket_id"] for t in stale])
                        else:
                            logger.debug("⏰ Background task: no stale unassigned tickets")
                except Exception as bg_exc:
                    logger.warning(f"⚠️ Alert background task error (non-fatal) | {bg_exc}")

                await asyncio.sleep(INTERVAL_SECONDS)

        asyncio.create_task(_unassigned_ticket_alert_task())
        logger.info("⏰ 30-min unassigned ticket alert task started")

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
    root_path=settings.ROOT_PATH,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail if isinstance(exc.detail, str) else str(exc.detail)},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    first_error = exc.errors()[0] if exc.errors() else {}
    msg = first_error.get("msg", "Invalid request payload")
    return JSONResponse(
        status_code=400,
        content={"message": msg},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception | {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "An unexpected error occurred. Please try again."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # HSTS for 1 year, including subdomains
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Prevent clickjacking (framing)
    response.headers["X-Frame-Options"] = "DENY"
    # Simple Content Security Policy
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    # XSS Protection (older browsers)
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response




from core.auth import get_current_user

# Public / Webhook routes (no global token required)
app.include_router(health.router,          prefix="/api/v1")
app.include_router(webhooks.router,        prefix="/api/v1/webhooks")
app.include_router(cal_webhooks.router,    prefix="/api/v1/webhooks")
app.include_router(invite.router,          prefix="/api/v1")

# Protected business logic routes (require token: Clerk JWT or Static API Key)
protected_deps = [Depends(get_current_user)]
app.include_router(chat.router,            prefix="/api/v1", dependencies=protected_deps)
app.include_router(conversations.router,   prefix="/api/v1", dependencies=protected_deps)
app.include_router(messages.router,        prefix="/api/v1", dependencies=protected_deps)
app.include_router(documents.router,       prefix="/api/v1", dependencies=protected_deps)
app.include_router(admin.router,           prefix="/api/v1", dependencies=protected_deps)
app.include_router(hitl.router,            prefix="/api/v1", dependencies=protected_deps)
app.include_router(cal_routes.router,      prefix="/api/v1", dependencies=protected_deps)
app.include_router(auth.router,            prefix="/api/v1", dependencies=protected_deps)
app.include_router(notes.router,           prefix="/api/v1", dependencies=protected_deps)

logger.info("FastAPI app created")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        loop="asyncio",
        log_level="info",
    )
# Reload trigger comment to refresh settings and clear schema caches.
