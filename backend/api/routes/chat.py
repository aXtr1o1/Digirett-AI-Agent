"""
api/routes/chat.py  — WebSocket streaming (no SSE)

Endpoint: ws://host/api/v1/chat/ws

The 403 was caused by FastAPI's WebSocket CORS rejection.
Fix: accept the connection first, THEN apply rate limiting.
FastAPI's CORSMiddleware does NOT apply to WebSocket routes —
WebSocket connections must be accepted unconditionally at the
handler level; origin checks (if needed) go inside the handler.

All business logic is identical to the original SSE _generate().
Only the transport changed:
    yield f"data: {json.dumps(event)}\n\n"  →  await websocket.send_json(event)
"""

import json
import logging
import time
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from schemas.requests import ChatRequest

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Services injected from main.py via set_services() ────────────────────────
_rag_service          = None
_conversation_service = None
_message_service      = None
_llm_service          = None


def set_services(rag_service, conversation_service, message_service, llm_service) -> None:
    global _rag_service, _conversation_service, _message_service, _llm_service
    _rag_service          = rag_service
    _conversation_service = conversation_service
    _message_service      = message_service
    _llm_service          = llm_service


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# In-process rate limiter
# slowapi does not support WebSocket routes — this replaces it.
# Same budget: 250 requests / 60 seconds / client IP.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class _RateLimiter:
    _WINDOW = 60
    _MAX    = 250

    def __init__(self):
        self._buckets: dict = defaultdict(list)

    def is_allowed(self, ip: str) -> bool:
        now    = time.time()
        cutoff = now - self._WINDOW
        self._buckets[ip] = [t for t in self._buckets[ip] if t > cutoff]
        if len(self._buckets[ip]) >= self._MAX:
            return False
        self._buckets[ip].append(now)
        return True


_rate_limiter = _RateLimiter()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WebSocket endpoint
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.websocket("/chat/ws")
async def chat_websocket(websocket: WebSocket):


    await websocket.accept()

    client_ip = websocket.client.host if websocket.client else "unknown"
    logger.info(f"🔌 WS connected | ip={client_ip}")

    if not _rate_limiter.is_allowed(client_ip):
        logger.warning(f"⛔ WS rate limit exceeded | ip={client_ip}")
        await websocket.send_json({"type": "error", "message": "Rate limit exceeded"})
        await websocket.close(code=1008, reason="Rate limit exceeded")
        return

    try:
        # Keep connection open — handle one query per received message
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info(f"🔌 WS disconnected cleanly | ip={client_ip}")
                break

            # Parse and validate
            try:
                payload      = json.loads(raw)
                chat_request = ChatRequest(**payload)
            except Exception as parse_exc:
                await websocket.send_json({
                    "type":    "error",
                    "message": f"Invalid request payload: {parse_exc}",
                })
                continue   # keep connection open, wait for next message

            # Process one full query and stream all events back
            await _handle_query(websocket, chat_request)

    except WebSocketDisconnect:
        pass  # clean disconnect
    except Exception as exc:
        logger.error(f"❌ WS fatal | ip={client_ip} | {exc}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        logger.info(f"🔌 WS session ended | ip={client_ip}")



async def _handle_query(websocket: WebSocket, chat_request: ChatRequest) -> None:
    start_time        = datetime.utcnow()
    conversation_id   = None
    full_answer       = ""
    intent            = "UNKNOWN"
    language          = "english"
    rag_chunks        = []
    is_first_exchange = False
    user_msg_id       = None
    assistant_msg_id  = None

    try:
        logger.info(f"💬 WS query: '{chat_request.query[:80]}'")

        # ── Step 1: Get or create conversation ────────────────
        conversation_id = chat_request.conversation_id
        user_id = chat_request.user_id or "2a06144d-4675-4c38-b7f8-13c02da91af5"

        if not conversation_id:
            conversation      = _conversation_service.create_conversation(
                user_id=user_id, title=None,
            )
            conversation_id   = conversation["conversation_id"]
            is_first_exchange = True
            logger.info(f"✅ Auto-created conversation: {conversation_id}")
        else:
            existing          = _message_service.get_conversation_messages(
                conversation_id=conversation_id, limit=1,
            )
            is_first_exchange = len(existing) == 0

    
        async for event in _rag_service.process_query(
            query=chat_request.query,
            conversation_id=conversation_id,
            top_k=chat_request.top_k,
        ):
            event_type = event.get("type")

            if event_type == "intent":
                intent   = event["data"]["intent"]
                language = event["data"]["language"]
                logger.info(f"🎯 Intent={intent}, Language={language}")
                await websocket.send_json(event)

            elif event_type == "token":
                full_answer += event["data"]
                await websocket.send_json(event)          

            elif event_type == "sources":
                rag_chunks = event.get("data", [])
                await websocket.send_json(event)

            elif event_type == "complete":
                metadata    = event["metadata"]
                full_answer = metadata.get("full_answer", full_answer)
                rag_chunks  = metadata.get("rag_chunks") or rag_chunks

                # Step 3: Save to Supabase + Redis (UNCHANGED)
                try:
                    query_time = (datetime.utcnow() - start_time).total_seconds()

                    chunks_to_save = []
                    if rag_chunks and isinstance(rag_chunks, list):
                        if rag_chunks and isinstance(rag_chunks[0], dict):
                            chunks_to_save = rag_chunks

                    user_msg_id, assistant_msg_id = _message_service.save_exchange(
                        conversation_id=conversation_id,
                        user_message=chat_request.query,
                        assistant_message=full_answer,
                        metadata={
                            "intent":           intent,
                            "language":         language,
                            "tokens_generated": metadata.get("tokens_generated", 0),
                            "query_time":       query_time,
                            "model":            "gpt-4o-mini",
                            "score":            metadata.get("score", 1.0),
                            "confidence":       metadata.get("confidence", "Unknown"),
                            "chunks_retrieved": metadata.get("chunks_retrieved", 0),
                        },
                        rag_chunks=chunks_to_save,
                        skip_save_user=chat_request.skip_save_user,
                    )
                    logger.info(
                        f"✅ Saved | user={user_msg_id} | assistant={assistant_msg_id}"
                    )
                    # After save_exchange succeeds, check if summary needs updating
                    await _rag_service._memory_agent.maybe_update_summary(
                        conversation_id=conversation_id,
                        llm_service=_llm_service,
                        conversation_service=_conversation_service,
                    )
                except Exception as save_exc:
                    logger.error(
                        f"❌ Save failed | conv={conversation_id} | {save_exc}",
                        exc_info=True,
                    )

                # Step 4: Auto-generate title after 2 user + 2 assistant messages
                try:
                    # Fetch first 10 messages in chronological order
                    msg_response = (
                        _message_service._supabase.table("messages")
                        .select("role, content")
                        .eq("conversation_id", conversation_id)
                        .order("created_at", desc=False)
                        .limit(10)
                        .execute()
                    )

                    all_msgs = msg_response.data or []

                    user_msgs = [m for m in all_msgs if m["role"] == "user"]
                    assistant_msgs = [m for m in all_msgs if m["role"] == "assistant"]

                    conversation = _conversation_service.get_conversation(conversation_id)

                    if (
                        len(user_msgs) >= 2
                        and len(assistant_msgs) >= 2
                        and conversation
                        and conversation.get("title") == "New conversation"
                    ):

                        # Take first 2 user + first 2 assistant messages
                        context = []
                        u_count = 0
                        a_count = 0

                        for m in all_msgs:
                            if m["role"] == "user" and u_count < 2:
                                context.append(m["content"])
                                u_count += 1
                            elif m["role"] == "assistant" and a_count < 2:
                                context.append(m["content"])
                                a_count += 1

                            if u_count == 2 and a_count == 2:
                                break

                        title = await _llm_service.generate_conversation_title(
                            first_user_message=context[0],
                            first_assistant_message=context[1],
                            second_user_message=context[2],
                            second_assistant_message=context[3],
                        )

                        _conversation_service.update_title(
                            conversation_id=conversation_id,
                            title=title,
                        )

                        metadata["conversation_title"] = title
                        logger.info(f"✅ Auto-title (2+2): '{title}'")

                except Exception as title_exc:
                    logger.warning(f"⚠️ Title generation failed | {title_exc}")


                # Step 5: Normalize sources (UNCHANGED)
                normalized_sources = []
                for chunk in (rag_chunks if isinstance(rag_chunks, list) else []):
                    if not isinstance(chunk, dict):
                        continue
                    url = chunk.get("url")
                    if not url:
                        continue
                    normalized_sources.append({
                        "title": chunk.get("file_name") or chunk.get("chunk_id") or "Source",
                        "url":   url,
                    })

                metadata["conversation_id"] = conversation_id
                metadata["message_id"]      = assistant_msg_id
                metadata["sources"]         = normalized_sources

                await websocket.send_json({"type": "complete", "metadata": metadata})

            elif event_type == "error":
                await websocket.send_json(event)

    except WebSocketDisconnect:
        logger.info(f"🔌 Client disconnected mid-stream | conv={conversation_id}")

    except Exception as exc:
        logger.error(
            f"❌ Query error | '{chat_request.query[:50]}' | conv={conversation_id} | {exc}",
            exc_info=True,
        )
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass    