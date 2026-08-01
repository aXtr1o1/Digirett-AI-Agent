"""
services/chat_orchestrator.py — WebSocket Chat Orchestration Service

Orchestrates WebSocket chat query execution:
  - _handle_quota()        : Rolling 4-hour quota checks
  - _handle_conversation() : Conversation creation & authorization
  - _handle_streaming()    : Token streaming & background citation translation
  - _handle_persistence()  : Persisting exchanges & source links
  - _handle_memory()       : Conversation summary & user fact extraction
  - _handle_title()        : Automatic title generation after 2nd exchange
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import WebSocket
from schemas.requests import ChatRequest

logger = logging.getLogger(__name__)


class ChatOrchestrator:

    def __init__(
        self,
        rag_service,
        conversation_service,
        message_service,
        llm_service,
        document_service,
        user_service,
        title_translation_service,
    ) -> None:
        self._rag_service = rag_service
        self._conversation_service = conversation_service
        self._message_service = message_service
        self._llm_service = llm_service
        self._document_service = document_service
        self._user_service = user_service
        self._translation_service = title_translation_service
        logger.info("[OK] ChatOrchestrator initialized")

    async def _send_ws_json(self, websocket: WebSocket, data: Dict[str, Any]) -> None:
        """Send JSON over WebSocket, safely handling UUID objects using default=str."""
        import json
        payload = json.dumps(data, default=str)
        await websocket.send_text(payload)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HANDLER STAGES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _handle_quota(self, websocket: WebSocket, user_id: str, user_role: str) -> bool:
        """Stage 1: Quota validation (turn & token limits). Returns True if allowed."""
        if not self._document_service:
            return True

        allowed_turn, _ = self._document_service.check_turn_limit(user_id, user_role=user_role)
        if not allowed_turn:
            logger.warning(f"⚠️ Quota exceeded (Turns) | user={user_id}")
            await self._send_ws_json(websocket, {
                "type": "error",
                "error_type": "quota_exceeded",
                "message": "Message limit reached. Your session resets every 4 hours.",
            })
            return False

        allowed_token, _ = self._document_service.check_token_limit(user_id, user_role=user_role)
        if not allowed_token:
            logger.warning(f"⚠️ Quota exceeded (Tokens) | user={user_id}")
            await self._send_ws_json(websocket, {
                "type": "error",
                "error_type": "quota_exceeded",
                "message": "Token limit reached. Your session resets every 4 hours.",
            })
            return False

        return True

    async def _handle_conversation(
        self,
        websocket: WebSocket,
        chat_request: ChatRequest,
        user_id: str,
        clerk_user,
    ) -> Tuple[Optional[str], bool]:
        """Stage 2: Get or create conversation and verify ownership."""
        conversation_id = chat_request.conversation_id
        is_first_exchange = False

        if not conversation_id:
            conv = self._conversation_service.create_conversation(user_id=user_id, title=None)
            conversation_id = conv["conversation_id"]
            is_first_exchange = True
            logger.info(f"ℹ️ Auto-created conversation: {conversation_id}")
        else:
            existing_conv = self._conversation_service.get_conversation(conversation_id)
            if not existing_conv:
                await self._send_ws_json(websocket, {"type": "error", "message": "Conversation not found"})
                return None, False

            if existing_conv.get("user_id") != user_id and clerk_user.role != "admin":
                await self._send_ws_json(websocket, {"type": "error", "message": "Not authorized to access this conversation"})
                return None, False

            existing = self._message_service.get_conversation_messages(conversation_id=conversation_id, limit=1)
            is_first_exchange = len(existing) == 0

        return conversation_id, is_first_exchange

    async def _translate_sources_bg(self, vs_list: List[Any], lang: str) -> List[Any]:
        """Helper for background citation translation."""
        try:
            src_urls = [s["url"] for s in vs_list if isinstance(s, dict) and s.get("url")]
            title_map_live = {}
            fetcher = self._message_service.get_title_fetcher()
            if src_urls and fetcher:
                try:
                    title_map_live = await fetcher.resolve_titles(src_urls)
                except Exception as e:
                    logger.warning(f"⚠️ Sources title resolve failed: {e}")

            norwegian_titles = [
                title_map_live.get(s["url"]) or s["url"] if isinstance(s, dict) and s.get("url") else ""
                for s in vs_list
            ]

            translated = await self._translation_service.translate_titles(
                titles=norwegian_titles,
                language=lang,
                urls=src_urls,
            )

            ts = []
            for idx, s in enumerate(vs_list):
                if isinstance(s, dict) and s.get("url"):
                    final_t = translated[idx]
                    if s.get("section_ref"):
                        final_t = f"{final_t} - {s['section_ref']}"
                    ts.append({"title": final_t, "url": s["url"], "section_ref": s.get("section_ref")})
                else:
                    ts.append(s)
            return ts
        except Exception as exc:
            logger.error(f"❌ Translation task failed: {exc}")
            return vs_list

    async def _handle_persistence(
        self,
        conversation_id: str,
        query: str,
        full_answer: str,
        intent: str,
        language: str,
        start_time: datetime,
        metadata: Dict[str, Any],
        rag_chunks: List[Any],
        skip_save_user: bool,
    ) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """Stage 4: Persists message exchange and sources to database."""
        try:
            query_time = (datetime.utcnow() - start_time).total_seconds()
            chunks_to_save = rag_chunks if (rag_chunks and isinstance(rag_chunks, list) and isinstance(rag_chunks[0], dict)) else []

            user_msg_id, assistant_msg_id, resolved_title_map = await self._message_service.save_exchange(
                conversation_id=conversation_id,
                user_message=query,
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
                    "detected_domain": metadata.get("detected_domain"),
                },
                rag_chunks=chunks_to_save,
                skip_save_user=skip_save_user,
            )
            logger.info(f"ℹ️ Saved exchange | user={user_msg_id} | assistant={assistant_msg_id}")
            return user_msg_id, assistant_msg_id, resolved_title_map
        except Exception as save_exc:
            logger.error(f"❌ Save failed | conv={conversation_id} | {save_exc}", exc_info=True)
            return None, None, {}

    async def _handle_memory(self, conversation_id: str, user_id: str, query: str) -> None:
        """Stage 5: Background conversation summary & user memory fact extraction."""
        try:
            summary_service = getattr(self._rag_service, "_summary_service", None) or getattr(self._rag_service, "_memory_agent", None)
            if summary_service and hasattr(summary_service, "maybe_update_summary"):
                await summary_service.maybe_update_summary(
                    conversation_id=conversation_id,
                    llm_service=self._llm_service,
                    conversation_service=self._conversation_service,
                )

            if hasattr(self._rag_service, "_user_memory_agent"):

                asyncio.create_task(
                    self._rag_service._user_memory_agent.extract_and_save_facts(
                        user_id=user_id,
                        message=query,
                        llm_service=self._llm_service,
                    )
                )
        except Exception as mem_exc:
            logger.warning(f"⚠️ Memory update failed (non-fatal) | {mem_exc}")

    async def _handle_title(self, conversation_id: str) -> Optional[str]:
        """Stage 6: Auto-generates conversation title after 2nd exchange."""
        try:
            all_msgs = self._message_service.get_first_messages(conversation_id=conversation_id, limit=10)
            user_msgs = [m for m in all_msgs if m.get("role") == "user"]
            assistant_msgs = [m for m in all_msgs if m.get("role") == "assistant"]

            conv = self._conversation_service.get_conversation(conversation_id)
            if len(user_msgs) >= 2 and len(assistant_msgs) >= 2 and conv and conv.get("title") == "New conversation":
                context = []
                u_c, a_c = 0, 0
                for m in all_msgs:
                    if m.get("role") == "user" and u_c < 2:
                        context.append(m["content"])
                        u_c += 1
                    elif m.get("role") == "assistant" and a_c < 2:
                        context.append(m["content"])
                        a_c += 1
                    if u_c == 2 and a_c == 2:
                        break

                title = await self._llm_service.generate_conversation_title(
                    first_user_message=context[0],
                    first_assistant_message=context[1],
                    second_user_message=context[2],
                    second_assistant_message=context[3],
                )
                self._conversation_service.update_title(conversation_id=conversation_id, title=title)
                logger.info(f"ℹ️ Auto-title generated (2+2): '{title}'")
                return title
        except Exception as title_exc:
            logger.warning(f"⚠️ Title generation failed (non-fatal) | {title_exc}")
        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MAIN ORCHESTRATION PIPELINE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def handle_chat_query(
        self,
        websocket: WebSocket,
        chat_request: ChatRequest,
        user_id: str,
        clerk_user,
    ) -> None:
        """Main orchestrator endpoint for processing a single WebSocket chat query."""
        start_time = datetime.utcnow()
        full_answer = ""
        intent = "UNKNOWN"
        language = "english"
        rag_chunks: List[Any] = []
        visible_sources: List[Any] = []
        titled_sources: List[Any] = []

        # 1. Quota Stage
        if not await self._handle_quota(websocket, user_id, clerk_user.role):
            return

        # 2. Conversation & Auth Stage
        conversation_id, _ = await self._handle_conversation(websocket, chat_request, user_id, clerk_user)
        if not conversation_id:
            return

        # 3. Streaming Stage
        try:
            translation_task = None
            async for event in self._rag_service.process_query(
                query=chat_request.query,
                conversation_id=conversation_id,
                user_id=user_id,
                top_k=chat_request.top_k,
            ):
                event_type = event.get("type")

                if event_type == "intent":
                    intent = event["data"]["intent"]
                    language = event["data"]["language"]
                    await self._send_ws_json(websocket, event)

                elif event_type == "token":
                    full_answer += event["data"]
                    await self._send_ws_json(websocket, event)

                elif event_type == "sources":
                    visible_sources = event.get("data", [])
                    rag_chunks = visible_sources
                    translation_task = asyncio.create_task(self._translate_sources_bg(visible_sources, language))

                elif event_type == "complete":
                    if translation_task:
                        titled_sources = await translation_task
                        await self._send_ws_json(websocket, {"type": "sources", "data": titled_sources})

                    metadata = event["metadata"]
                    full_answer = metadata.get("full_answer", full_answer)
                    rag_chunks = metadata.get("rag_chunks") or rag_chunks

                    # 4. Persistence Stage
                    _, assistant_msg_id, resolved_title_map = await self._handle_persistence(
                        conversation_id=conversation_id,
                        query=chat_request.query,
                        full_answer=full_answer,
                        intent=intent,
                        language=language,
                        start_time=start_time,
                        metadata=metadata,
                        rag_chunks=rag_chunks,
                        skip_save_user=chat_request.skip_save_user,
                    )

                    # 5. Memory Stage
                    await self._handle_memory(conversation_id, user_id, chat_request.query)

                    # 6. Title Stage
                    gen_title = await self._handle_title(conversation_id)
                    if gen_title:
                        metadata["conversation_title"] = gen_title

                    # Build normalized sources payload
                    seen_urls: set = set()
                    normalized_sources = []
                    for src in (titled_sources if titled_sources else []):
                        if not isinstance(src, dict) or not src.get("url"):
                            continue
                        url = src["url"]
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)

                        best_title = src.get("title") or resolved_title_map.get(url) or url
                        normalized_sources.append({"title": best_title, "url": url})

                    metadata["conversation_id"] = conversation_id
                    metadata["message_id"] = assistant_msg_id
                    metadata["sources"] = normalized_sources

                    if assistant_msg_id and normalized_sources:
                        self._message_service.update_message_sources(assistant_msg_id, normalized_sources)

                    await self._send_ws_json(websocket, {"type": "complete", "metadata": metadata})

                    # Update turn and token quota counts
                    if self._document_service:
                        self._document_service.increment_turn_count(user_id)
                        total_tokens = (len(chat_request.query) // 4) + (len(full_answer) // 4)
                        self._document_service.increment_token_count(user_id, total_tokens)

                elif event_type == "error":
                    await self._send_ws_json(websocket, event)

        except Exception as exc:
            logger.error(f"❌ Query execution error | conv={conversation_id} | {exc}", exc_info=True)
            try:
                await self._send_ws_json(websocket, {"type": "error", "message": str(exc)})
            except Exception:
                pass
