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

from api.routes import admin, auth, chat, conversations, documents, health, hitl, invite, messages, webhooks, ratings, library, ticket_messages, billing
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
from services.library_service import LibraryService
from services.stripe_gateway import StripeGateway
from services.billing_service import BillingService
from services.invite_service import InviteService
from services.notification_service import NotificationService
from services.rating_service import RatingService
from services.subscription_service import SubscriptionService
from services.ticket_message_service import TicketMessageService
from services.title_translation_service import TitleTranslationService
from services.webhook_service import WebhookService


from services.chat_orchestrator import ChatOrchestrator


from startup.database import init_database_connections
from startup.services import init_and_register_services
from startup.routes import setup_routes_and_middleware
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
        # 1. Connect to Database Infrastructure
        milvus_client, redis_client, supabase_client = init_database_connections()

        # 2. Instantiate and Register Services onto app.state
        init_and_register_services(
            app=app,
            milvus_client=milvus_client,
            redis_client=redis_client,
            supabase_client=supabase_client,
        )

        health.set_clients(
            milvus=milvus_client,
            redis=redis_client,
            supabase=supabase_client,
            llm=app.state.llm_service,
        )

        admin.set_services(
            user_svc=app.state.user_service,
            email_svc=app.state.email_service,
            hitl_svc=app.state.hitl_service,
        )
        hitl.set_services(
            hitl_svc=app.state.hitl_service,
            user_svc=app.state.user_service,
            email_svc=app.state.email_service,
        )

        logger.info("All services ready — server is live")

        async def _unassigned_ticket_alert_task():
            INTERVAL_SECONDS = 30 * 60
            await asyncio.sleep(60)
            while True:
                try:
                    admin_email = settings.ADMIN_ALERT_EMAIL
                    if admin_email and hasattr(app.state, "hitl_service"):
                        stale = app.state.hitl_service.get_unassigned_tickets_older_than_minutes(minutes=30)
                        if stale:
                            logger.info(f" Background task: {len(stale)} unassigned tickets older than 30min — alerting admin")
                            await app.state.email_service.send_admin_unassigned_alert(
                                admin_email=admin_email,
                                unassigned_tickets=stale,
                            )
                            app.state.hitl_service.mark_alert_sent([t["ticket_id"] for t in stale])
                except Exception as bg_exc:
                    logger.warning(f" Alert background task error (non-fatal) | {bg_exc}")

                await asyncio.sleep(INTERVAL_SECONDS)

        asyncio.create_task(_unassigned_ticket_alert_task())

        async def _auto_close_tickets_task():
            INTERVAL_SECONDS = 15 * 60
            await asyncio.sleep(120)
            while True:
                try:
                    if hasattr(app.state, "hitl_service"):
                        closed_count = app.state.hitl_service.auto_close_stale_resolved_tickets()
                        if closed_count > 0:
                            logger.info(f" Auto-closed {closed_count} stale resolved tickets.")
                except Exception as bg_exc:
                    logger.warning(f" Auto-close background task error (non-fatal) | {bg_exc}")
                await asyncio.sleep(INTERVAL_SECONDS)

        asyncio.create_task(_auto_close_tickets_task())

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
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Digirett AI Agent API",
        version="2.0.0",
        description="Legal AI Assistant API with RAG & HITL workflows",
        routes=app.routes,
    )
    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your Clerk JWT token or Static BACKEND_API_KEY (non-prod) here."
        }
    }
    # Attach security requirement to all protected routes in OpenAPI schema
    for path, path_item in openapi_schema.get("paths", {}).items():
        if not path.startswith("/api/v1/health") and not path.startswith("/api/v1/webhooks") and not path.startswith("/api/v1/invite"):
            for method in path_item:
                if isinstance(path_item[method], dict):
                    path_item[method]["security"] = [{"HTTPBearer": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

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
app.include_router(billing.router,         prefix="/api/v1", dependencies=protected_deps)
app.include_router(notes.router,           prefix="/api/v1", dependencies=protected_deps)
app.include_router(ratings.router,         prefix="/api/v1", dependencies=protected_deps)
app.include_router(library.router,         prefix="/api/v1", dependencies=protected_deps)
app.include_router(ticket_messages.router,  prefix="/api/v1", dependencies=protected_deps)

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