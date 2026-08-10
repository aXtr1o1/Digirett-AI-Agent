import json
import logging
import time
from collections import defaultdict
from typing import Optional
from config import settings


from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status

from core.auth import verify_ws_token
from schemas.requests import ChatRequest
from services.chat_orchestrator import ChatOrchestrator
from services.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter()

def get_chat_orchestrator(request: Request) -> ChatOrchestrator:
    orchestrator = getattr(request.app.state, "chat_orchestrator", None)
    if orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ChatOrchestrator is not initialized on application state.",
        )
    return orchestrator


def get_user_service(request: Request) -> UserService:
    user_svc = getattr(request.app.state, "user_service", None)
    if user_svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UserService is not initialized on application state.",
        )
    return user_svc

class _RateLimiter:
    def __init__(self):
        self._window = getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)
        self._max = getattr(settings, "RATE_LIMIT_MAX_REQUESTS", 250)
        self._buckets: dict = defaultdict(list)
    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        cutoff = now - self._window
        self._buckets[ip] = [t for t in self._buckets[ip] if t > cutoff]
        if len(self._buckets[ip]) >= self._max:
            return False
        self._buckets[ip].append(now)
        return True


_rate_limiter = _RateLimiter()


from schemas.responses import ChatResponse

@router.post(
    "/chat/stream",
    response_model=ChatResponse,
    tags=["Chat"],
    summary="Chat Query Endpoint (Documentation & Non-Streaming Fallback)",
    description="Main chat streaming endpoint. Primary real-time execution runs via WebSocket at `/api/v1/chat/ws?token=<token>`. This HTTP POST endpoint serves Swagger UI documentation and testing.",
)
async def chat_stream_doc(chat_request: ChatRequest):
    return ChatResponse(
        answer="Real-time legal streaming operates via WebSocket at /api/v1/chat/ws. Pass your query in the JSON payload.",
        conversation_id=chat_request.conversation_id,
    )



@router.websocket("/chat/ws")
async def chat_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time legal assistant streaming.
    Applies rate limiting, verifies JWT authentication token,
    and delegates query orchestration to ChatOrchestrator.
    """
    await websocket.accept()

    client_ip = websocket.client.host if websocket.client else "unknown"
    logger.info(f"🔌 WS connected | ip={client_ip}")

    # 1. Rate Limit Check
    if not _rate_limiter.is_allowed(client_ip):
        logger.warning(f" WS rate limit exceeded | ip={client_ip}")
        await websocket.send_json({"type": "error", "message": "Rate limit exceeded"})
        await websocket.close(code=1008, reason="Rate limit exceeded")
        return

    # 2. Extract & Verify Token
    token = websocket.query_params.get("token")
    if not token:
        logger.warning(f" WS connection rejected (Missing token) | ip={client_ip}")
        await websocket.send_json({"type": "error", "message": "Authentication token is required"})
        await websocket.close(code=1008, reason="Authentication failed")
        return

    clerk_user = await verify_ws_token(token)
    if not clerk_user:
        logger.warning(f" WS connection rejected (Invalid token) | ip={client_ip}")
        await websocket.send_json({"type": "error", "message": "Invalid authentication token"})
        await websocket.close(code=1008, reason="Authentication failed")
        return

    # 3. Resolve ChatOrchestrator & UserService from app.state
    orchestrator: Optional[ChatOrchestrator] = getattr(websocket.app.state, "chat_orchestrator", None)
    user_service: Optional[UserService] = getattr(websocket.app.state, "user_service", None)

    if not orchestrator or not user_service:
        logger.error(" WS rejected: Services not initialized on app.state")
        await websocket.send_json({"type": "error", "message": "Chat service unavailable"})
        await websocket.close(code=1011, reason="Service unavailable")
        return

    internal_user_id = user_service.get_user_id_from_clerk_id(clerk_user.clerk_user_id)
    if not internal_user_id:
        logger.warning(f" WS connection rejected (User not found) | clerk_id={clerk_user.clerk_user_id}")
        await websocket.send_json({"type": "error", "message": "User profile not found"})
        await websocket.close(code=1008, reason="Authentication failed")
        return

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info(f"🔌 WS disconnected cleanly | ip={client_ip}")
                break

            try:
                payload = json.loads(raw)
                chat_request = ChatRequest(**payload)
            except Exception as parse_exc:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Invalid request payload: {parse_exc}",
                })
                continue

            # Delegate query execution to ChatOrchestrator
            await orchestrator.handle_chat_query(
                websocket=websocket,
                chat_request=chat_request,
                user_id=internal_user_id,
                clerk_user=clerk_user,
            )

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(f" WS fatal error | ip={client_ip} | {exc}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        logger.info(f" WS session ended | ip={client_ip}")