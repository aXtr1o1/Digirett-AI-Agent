"""
startup/routes.py — Route inclusion and Middleware Registration
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.routes import (
    admin,
    auth,
    billing,
    cal as cal_routes,
    cal_webhooks,
    chat,
    conversations,
    documents,
    health,
    hitl,
    invite,
    library,
    messages,
    notes,
    ratings,
    ticket_messages,
    webhooks,
)
from config import settings

logger = logging.getLogger(__name__)


def setup_routes_and_middleware(app: FastAPI, limiter: Limiter) -> None:
    """
    Attach CORS middleware, rate limiters, and include all APIRouters.
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(conversations.router, prefix="/api/v1")
    app.include_router(messages.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(hitl.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(webhooks.router, prefix="/api/v1")
    app.include_router(cal_routes.router, prefix="/api/v1")
    app.include_router(cal_webhooks.router, prefix="/api/v1")
    app.include_router(ratings.router, prefix="/api/v1")
    app.include_router(notes.router, prefix="/api/v1")
    app.include_router(library.router, prefix="/api/v1")
    app.include_router(ticket_messages.router, prefix="/api/v1")
    app.include_router(billing.router, prefix="/api/v1")
    app.include_router(invite.router, prefix="/api/v1")

    logger.info("[OK] All APIRouters and CORS middleware configured")
