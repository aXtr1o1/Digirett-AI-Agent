
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from schemas.requests import ChatRequest

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# Injected from main.py via set_services()
_rag_service = None
_conversation_service = None
_message_service = None
_llm_service = None


def set_services(rag_service, conversation_service, message_service, llm_service) -> None:
    global _rag_service, _conversation_service, _message_service, _llm_service
    _rag_service = rag_service
    _conversation_service = conversation_service
    _message_service = message_service
    _llm_service = llm_service


@router.post(
    "/chat/stream",
    tags=["RAG"],
    summary="Stream a RAG-powered answer via SSE",
)
@limiter.limit("250/minute")
async def chat_stream(request: Request, chat_request: ChatRequest):
    

    async def _generate():
        start_time = datetime.utcnow()
        conversation_id = None
        full_answer = ""
        intent = "UNKNOWN"
        language = "english"
        rag_chunks = []
        is_first_exchange = False

        try:
            logger.info(f" Chat stream request: '{chat_request.query[:80]}'")

            # ── Step 1: Get or create conversation ────────────────────────
            conversation_id = chat_request.conversation_id
            user_id = chat_request.user_id

            if not conversation_id:
                conversation = _conversation_service.create_conversation(
                    user_id=user_id,
                    title=None,   # Title will be auto-generated after first exchange
                )
                conversation_id = conversation["conversation_id"]
                is_first_exchange = True
                logger.info(f" Auto-created conversation: {conversation_id}")
            else:
                # Check if this is the first real exchange in an existing conversation
                existing = _message_service.get_conversation_messages(
                    conversation_id=conversation_id,
                    limit=1,
                )
                is_first_exchange = len(existing) == 0

            # ── Step 2: Process with RAGService ───────────────────────────
            async for event in _rag_service.process_query(
                query=chat_request.query,
                conversation_id=conversation_id,
                top_k=chat_request.top_k,
            ):
                event_type = event.get("type")

                if event_type == "intent":
                    intent = event["data"]["intent"]
                    language = event["data"]["language"]
                    logger.info(f"🎯 Intent={intent}, Language={language}")

                elif event_type == "token":
                    full_answer += event["data"]
                    yield f"data: {json.dumps(event)}\n\n"

                elif event_type == "sources":
                    rag_chunks = event.get("data", [])
                    yield f"data: {json.dumps(event)}\n\n"

                elif event_type == "complete":
                    metadata = event["metadata"]
                    full_answer = metadata.get("full_answer", full_answer)
                    rag_chunks = metadata.get("rag_chunks") or rag_chunks

                    # ── Step 3: Save exchange to Supabase + Redis ──────────
                    user_msg_id = None
                    assistant_msg_id = None

                    try:
                        query_time = (datetime.utcnow() - start_time).total_seconds()

                        # Only pass rag_chunks when they are actual chunk dicts
                        chunks_to_save = []
                        if rag_chunks and isinstance(rag_chunks, list):
                            if rag_chunks and isinstance(rag_chunks[0], dict):
                                chunks_to_save = rag_chunks

                        user_msg_id, assistant_msg_id = _message_service.save_exchange(
                            conversation_id=conversation_id,
                            user_message=chat_request.query,
                            assistant_message=full_answer,
                            metadata={
                                "intent": intent,
                                "language": language,
                                "tokens_generated": metadata.get("tokens_generated", 0),
                                "query_time": query_time,
                                "model": "gpt-4o-mini",
                                "score": metadata.get("score", 1.0),
                                "confidence": metadata.get("confidence", "Unknown"),
                                "chunks_retrieved": metadata.get("chunks_retrieved", 0),
                            },
                            rag_chunks=chunks_to_save,
                        )
                        logger.info(
                            f" User and AI message saved | user={user_msg_id} | assistant={assistant_msg_id}"
                        )
                    except Exception as save_exc:
                        logger.error(
                            f" Save User and AI message failed | conversation={conversation_id} | {save_exc}",
                            exc_info=True,
                        )

                    # ── Step 4: Auto-generate conversation title ───────────
                    # Only on the first exchange and only when we have an answer
                    if is_first_exchange and full_answer and assistant_msg_id:
                        try:
                            title = await _llm_service.generate_conversation_title(
                                first_user_message=chat_request.query,
                                first_assistant_message=full_answer,
                            )
                            _conversation_service.update_title(
                                conversation_id=conversation_id,
                                title=title,
                            )
                            metadata["conversation_title"] = title
                            logger.info(f" Auto-title set: '{title}'")
                        except Exception as title_exc:
                            logger.warning(f" Title generation failed | {title_exc}")

                    # ── Step 5: Normalize sources for the frontend ─────────
                    normalized_sources = []
                    for chunk in (rag_chunks if isinstance(rag_chunks, list) else []):
                        if not isinstance(chunk, dict):
                            continue
                        url = chunk.get("url")
                        if not url:
                            continue
                        normalized_sources.append({
                            "title": chunk.get("file_name") or chunk.get("chunk_id") or "Source",
                            "url": url,
                        })

                    metadata["conversation_id"] = conversation_id
                    metadata["message_id"] = assistant_msg_id
                    metadata["sources"] = normalized_sources

                    yield f"data: {json.dumps({'type': 'complete', 'metadata': metadata})}\n\n"

                elif event_type == "error":
                    yield f"data: {json.dumps(event)}\n\n"

        except Exception as exc:
            logger.error(
                f" Stream error | query='{chat_request.query[:50]}' | "
                f"conversation={conversation_id} | {exc}",
                exc_info=True,
            )
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )