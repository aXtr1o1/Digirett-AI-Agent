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
from typing import Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from langchain_core.messages import HumanMessage, SystemMessage
import asyncio

from core.auth import verify_ws_token
from schemas.requests import ChatRequest

from schemas.requests import ChatRequest

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Services injected from main.py via set_services() ────────────────────────
_rag_service          = None
_conversation_service = None
_message_service      = None
_llm_service          = None


_user_service         = None
_document_service     = None


def set_services(rag_service, conversation_service, message_service, llm_service, document_service, user_service=None) -> None:
    global _rag_service, _conversation_service, _message_service, _llm_service, _document_service, _user_service
    _rag_service          = rag_service
    _conversation_service = conversation_service
    _message_service      = message_service
    _llm_service          = llm_service
    _document_service     = document_service
    _user_service         = user_service
    
    # We load user_service to get the internal user ID. 
    # Optional parameter because of circular init ordering in main.py, but it will be set.
    from services.user_service import UserService
    from main import app
    # We can also get it from global imports if injected properly.
    _user_service = user_service


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
# Citation title translator
# WHY THIS FUNCTION EXISTS:
# Lovdata HTML titles are always in Norwegian (e.g. "Lov om foretaksregisteret").
# When the intent agent detects the user's query language as "english" we must
# translate those titles so the Sources panel matches the response language.
# We do this with ONE batched LLM call that handles all source titles at once.
# If language is "norwegian" we skip the call entirely — zero extra latency.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _translate_titles_for_language(
    titles: List[str],
    language: str,
    llm,              # AzureChatOpenAI instance from _llm_service._llm
    urls: List[str] = None,        # parallel list of URLs (for Redis keying)
    redis_client=None,             # RedisClient — for cache read/write
) -> List[str]:
    """
    Translate a list of Lovdata titles into `language`.

    Cache strategy (two layers):
      L1 Redis  : key = lovdata_title_translated:{lang}:{url}   TTL 7 days
                  Checked per-URL before the LLM call so already-known
                  translations are free.
      L2 LLM    : ONE batched call for all cache-miss URLs.
                  Result stored back to Redis (L1 back-fill).

    - language == "norwegian"  → returns titles unchanged (no LLM call, no cache).
    - On any error             → returns original titles (graceful fallback).
    """
    if not titles:
        return titles

    # Norwegian is the native Lovdata language — no translation needed.
    if language.lower() in ("norwegian", "norsk", "nb", "no"):
        logger.debug("🌐 Citation titles: language=norwegian — skipping translation")
        return titles

    _TRANSLATED_TTL = 604_800  # 7 days — same as Norwegian title cache
    lang_key = language.lower().replace(" ", "_")  # e.g. "english"

    def _redis_translated_key(url: str) -> str:
        return f"lovdata_title_translated:{lang_key}:{url}"

    def _redis_get_translated(url: str):
        if not redis_client or not url:
            return None
        try:
            val = redis_client._client.get(_redis_translated_key(url))
            return val if isinstance(val, str) else (val.decode() if val else None)
        except Exception:
            return None

    def _redis_set_translated(url: str, title: str) -> None:
        if not redis_client or not url:
            return
        try:
            redis_client._client.setex(_redis_translated_key(url), _TRANSLATED_TTL, title)
        except Exception:
            pass

    try:
        # ── L1: Redis cache — check each URL individually ───────────────────
        result = list(titles)           # copy — will fill from cache or LLM
        need_llm_idx: List[int] = []    # indices that missed the cache
        need_llm_titles: List[str] = [] # Norwegian titles to translate

        for i, (title, url) in enumerate(zip(titles, (urls or [None]*len(titles)))):
            cached = _redis_get_translated(url) if url else None
            if cached:
                result[i] = cached
                logger.debug(f"🌐 Redis hit translated | {url} → '{cached[:60]}'")
            else:
                need_llm_idx.append(i)
                need_llm_titles.append(title)

        if not need_llm_titles:
            logger.info(f"🌐 All {len(titles)} titles served from Redis cache | lang={language}")
            return result

        # ── L2: ONE batched LLM call for cache-miss titles ────────────────
        numbered_input = "\n".join(f"{i+1}. {t}" for i, t in enumerate(need_llm_titles))

        system_prompt = (
            "You are a legal document title translator. "
            "Translate each Norwegian legal document title to the requested language. "
            "Return ONLY a numbered list in the exact same order — one title per line. "
            "No explanations, no extra text, no blank lines between items."
        )
        user_prompt = (
            f"Translate the following Norwegian legal titles to {language}:\n\n"
            f"{numbered_input}\n\n"
            "Return only the numbered list of translated titles."
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = await llm.agenerate([messages])
        raw_output = response.generations[0][0].text.strip()

        # Parse the numbered list back into a plain list.
        translated_batch: List[str] = []
        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue
            import re
            cleaned = re.sub(r'^\d+\.\s*', '', line).strip()
            if cleaned:
                translated_batch.append(cleaned)

        if len(translated_batch) != len(need_llm_titles):
            logger.warning(
                f"⚠️  Citation translation returned {len(translated_batch)} items "
                f"for {len(need_llm_titles)} titles — using originals for missed"
            )
            # Fill what we have; keep originals for the rest
            for j, orig_idx in enumerate(need_llm_idx):
                if j < len(translated_batch):
                    result[orig_idx] = translated_batch[j]
            return result

        # Merge LLM results back + store in Redis
        for j, orig_idx in enumerate(need_llm_idx):
            translated = translated_batch[j]
            result[orig_idx] = translated
            # Back-fill Redis cache for this URL
            url = (urls or [None]*len(titles))[orig_idx]
            if url:
                _redis_set_translated(url, translated)
                logger.debug(f"🌐 Redis store translated | {url} → '{translated[:60]}'")

        logger.info(
            f"🌐 Citation titles translated to '{language}' | "
            f"llm={len(need_llm_titles)} | cache_hit={len(titles)-len(need_llm_idx)}"
        )
        return result

    except Exception as exc:
        logger.warning(f"⚠️  Citation title translation failed (non-fatal) | {exc}")
        return titles  # graceful fallback — show Norwegian rather than crash


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WebSocket endpoint
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.websocket("/chat/ws")
async def chat_websocket(websocket: WebSocket):


    await websocket.accept()

    client_ip = websocket.client.host if websocket.client else "unknown"
    logger.info(f"🔌 WS connected | ip={client_ip}")

    # 1. Check Rate Limit
    if not _rate_limiter.is_allowed(client_ip):
        logger.warning(f"⛔ WS rate limit exceeded | ip={client_ip}")
        await websocket.send_json({"type": "error", "message": "Rate limit exceeded"})
        await websocket.close(code=1008, reason="Rate limit exceeded")
        return

    # 2. Extract Token and Verify
    token = websocket.query_params.get("token")
    if not token:
        logger.warning(f"⛔ WS connection rejected (Missing token) | ip={client_ip}")
        await websocket.send_json({"type": "error", "message": "Authentication token is required"})
        await websocket.close(code=1008, reason="Authentication failed")
        return

    clerk_user = await verify_ws_token(token)
    if not clerk_user:
        logger.warning(f"⛔ WS connection rejected (Invalid token) | ip={client_ip}")
        await websocket.send_json({"type": "error", "message": "Invalid authentication token"})
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    # 3. Resolve Internal User ID
    # Import _user_service dynamically if not set
    global _user_service
    if not _user_service:
        # Fallback if not injected properly
        pass
    
    internal_user_id = None
    if _user_service:
        internal_user_id = await asyncio.to_thread(
            _user_service.get_user_id_from_clerk_id, 
            clerk_user.clerk_user_id, 
            clerk_user.email
        )
        
    if not internal_user_id:
        logger.warning(f"⛔ WS connection rejected (User not found) | clerk_id={clerk_user.clerk_user_id}")
        await websocket.send_json({"type": "error", "message": "User profile not found"})
        await websocket.close(code=1008, reason="Authentication failed")
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
            await _handle_query(websocket, chat_request, internal_user_id, clerk_user)

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



async def _handle_query(websocket: WebSocket, chat_request: ChatRequest, user_id: str, clerk_user) -> None:
    start_time        = datetime.utcnow()
    conversation_id   = None
    full_answer       = ""
    intent            = "UNKNOWN"
    language          = "english"
    rag_chunks        = []
    visible_sources   = []   # full list from sources event (includes §section URLs)
    titled_sources    = []   # same list but with resolved titles, sent over WS
    is_first_exchange = False
    user_msg_id       = None
    assistant_msg_id  = None

    try:
        logger.info(f"💬 WS query: '{chat_request.query[:80]}'")

        # ── Step 1: Enforce Quotas FIRST (Before creating a conversation) ─────
        if _document_service:
            role = clerk_user.role
            # 1. Check Turn Limit
            allowed_turn, turns_rem = _document_service.check_turn_limit(user_id, user_role=role)
            if not allowed_turn:
                logger.warning(f"🚫 Quota exceeded (Turns) | user={user_id}")
                await websocket.send_json({
                    "type": "error", 
                    "error_type": "quota_exceeded",
                    "message": f"Message limit reached. Your session resets every 4 hours."
                })
                return

            # 2. Check Token Limit
            allowed_token, tokens_rem = _document_service.check_token_limit(user_id, user_role=role)
            if not allowed_token:
                logger.warning(f"🚫 Quota exceeded (Tokens) | user={user_id}")
                await websocket.send_json({
                    "type": "error", 
                    "error_type": "quota_exceeded",
                    "message": f"Token limit reached. Your session resets every 4 hours."
                })
                return

        # ── Step 2: Get or create conversation ────────────────
        conversation_id = chat_request.conversation_id

        if not conversation_id:
            conversation      = _conversation_service.create_conversation(
                user_id=user_id, title=None,
            )
            conversation_id   = conversation["conversation_id"]
            is_first_exchange = True
            logger.info(f"✅ Auto-created conversation: {conversation_id}")
        else:
            # Add authorization check for existing conversation
            existing_conv = _conversation_service.get_conversation(conversation_id)
            if not existing_conv:
                await websocket.send_json({"type": "error", "message": "Conversation not found"})
                return
            if existing_conv.get("user_id") != user_id and clerk_user.role != "admin":
                await websocket.send_json({"type": "error", "message": "Not authorized to access this conversation"})
                return

            existing = _message_service.get_conversation_messages(
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
                visible_sources = event.get("data", [])
                rag_chunks = visible_sources  # keep rag_chunks in sync for legacy code

                async def _translate_sources_bg(vs_list, lang, llm, fetcher, cache):
                    try:
                        _src_urls = [s["url"] for s in vs_list if isinstance(s, dict) and s.get("url")]
                        _title_map_live = {}
                        if _src_urls and fetcher:
                            try:
                                _title_map_live = await fetcher.resolve_titles(_src_urls)
                            except Exception as e:
                                logger.warning(f"Sources title resolve failed: {e}")

                        _norwegian_titles = [
                            _title_map_live.get(s["url"]) or s["url"] if isinstance(s, dict) and s.get("url") else ""
                            for s in vs_list
                        ]

                        _translated = await _translate_titles_for_language(
                            titles=_norwegian_titles,
                            language=lang,
                            llm=llm,
                            urls=_src_urls,
                            redis_client=cache,
                        )

                        ts = []
                        for idx, s in enumerate(vs_list):
                            if isinstance(s, dict) and s.get("url"):
                                final_t = _translated[idx]
                                if s.get("section_ref"):
                                    final_t = f"{final_t} - {s['section_ref']}"
                                ts.append({"title": final_t, "url": s["url"], "section_ref": s.get("section_ref")})
                            else:
                                ts.append(s)
                        return ts
                    except Exception as e:
                        logger.error(f"Translation task failed: {e}")
                        return vs_list

                # Launch translation in background without blocking the token stream
                translation_task = asyncio.create_task(
                    _translate_sources_bg(
                        visible_sources, 
                        language, 
                        _llm_service._llm, 
                        getattr(_message_service, "_title_fetcher", None),
                        getattr(_message_service, "_cache", None)
                    )
                )

            elif event_type == "complete":
                # Ensure translation is done before completing
                titled_sources = []
                if "translation_task" in locals():
                    titled_sources = await translation_task
                    await websocket.send_json({"type": "sources", "data": titled_sources})

                metadata    = event["metadata"]
                full_answer = metadata.get("full_answer", full_answer)
                rag_chunks  = metadata.get("rag_chunks") or rag_chunks

                # Step 3: Save to Supabase + Redis (UNCHANGED)
                # NOTE: titled_sources was populated in the 'sources' handler above.
                # _resolved_title_map is filled by save_exchange return below.
                _resolved_title_map: dict = {}
                try:
                    query_time = (datetime.utcnow() - start_time).total_seconds()

                    chunks_to_save = []
                    if rag_chunks and isinstance(rag_chunks, list):
                        if rag_chunks and isinstance(rag_chunks[0], dict):
                            chunks_to_save = rag_chunks

                    user_msg_id, assistant_msg_id, _resolved_title_map = await _message_service.save_exchange(
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


                # Step 5: Sources for the WebSocket 'complete' event.
                # titled_sources was built in the 'sources' handler above and
                # ALREADY has translated titles (from _translate_titles_for_language).
                # Priority: translated title from titled_sources > Norwegian fallback
                # from _resolved_title_map. Do NOT put _resolved_title_map first —
                # it returns raw Norwegian titles from Lovdata HTML.
                _seen_s5: set = set()
                normalized_sources = []
                for src in (titled_sources if titled_sources else []):
                    if not isinstance(src, dict) or not src.get("url"):
                        continue
                    url = src["url"]
                    if url in _seen_s5:
                        continue
                    _seen_s5.add(url)
                    # ✅ FIX: prefer the already-translated title from titled_sources.
                    # _resolved_title_map is Norwegian (raw Lovdata HTML) — only use
                    # it as a last resort if titled_sources somehow has no title.
                    best_title = src.get("title")
                    if not best_title:
                        best_title = _resolved_title_map.get(url)
                        if best_title and src.get("section_ref"):
                            best_title = f"{best_title} - {src['section_ref']}"
                    
                    if not best_title:
                        best_title = url

                    normalized_sources.append({"title": best_title, "url": url})

                metadata["conversation_id"] = conversation_id
                metadata["message_id"]      = assistant_msg_id
                metadata["sources"]         = normalized_sources

                # ── Persist translated titles to Supabase ─────────────────────
                # WHY: save_exchange() saves Norwegian titles from title_fetcher.
                # On page refresh, messages reload from Supabase — if we don't
                # overwrite, users always see Norwegian titles after a reload.
                # We also fix missing URLs here: normalized_sources has ALL URLs
                # (section-anchor + base), while save_exchange only gets the 3
                # base-URL rag_chunks. Patching with the full list fixes both.
                if assistant_msg_id and normalized_sources:
                    try:
                        _message_service._supabase.table("messages").update(
                            {"sources": normalized_sources}
                        ).eq("message_id", assistant_msg_id).execute()
                        logger.info(
                            f"🌐 Persisted {len(normalized_sources)} translated sources "
                            f"to Supabase | msg={assistant_msg_id}"
                        )
                    except Exception as _persist_exc:
                        logger.warning(
                            f"⚠️  Failed to persist translated sources (non-fatal) | {_persist_exc}"
                        )

                await websocket.send_json({"type": "complete", "metadata": metadata})

                # ── Step 6: Update Quota Counters ─────────────────────
                if _document_service:
                    _document_service.increment_turn_count(user_id)
                    
                    # Approximate token count (chars / 4 is a common heuristic)
                    # Input tokens (query) + Output tokens (full_answer)
                    input_tokens = len(chat_request.query) // 4
                    output_tokens = len(full_answer) // 4
                    _document_service.increment_token_count(user_id, input_tokens + output_tokens)

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