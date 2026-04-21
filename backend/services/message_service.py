
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from db.redis_client import RedisClient
from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


class MessageService:
    

    def __init__(
        self,
        supabase_client: SupabaseClient,
        redis_client: RedisClient,
    ) -> None:
        self._supabase = supabase_client
        self._cache = redis_client
        logger.info(" MessageService initialized")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # READING MESSAGES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_conversation_messages(
    self,
    conversation_id: str,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    
        try:
            response = (
                self._supabase.table("messages")
                .select(
                    "message_id, conversation_id, role, content, "
                    "sources, metadata, created_at, type, file_name"
                )
                .eq("conversation_id", conversation_id)
                .or_("is_deleted.is.null,is_deleted.eq.false")
                .order("created_at", desc=False)
                .range(offset, offset + limit - 1)
                .execute()
            )
            messages = response.data or []

            for msg in messages:
                if msg["role"] == "assistant":
                    msg["sources"] = self._normalize_sources(msg.get("sources") or [])
                    # Strip <think> tags from assistant content
                    if msg.get("content"):
                        import re
                        msg["content"] = re.sub(
                            r'<think>.*?</think>', '', msg["content"], flags=re.DOTALL
                        ).strip()
                else:
                    msg["sources"] = []

                # Ensure type and file_name are always present for frontend
                msg["type"]      = msg.get("type") or "text"
                msg["file_name"] = msg.get("file_name")

            return messages

        except Exception as exc:
            logger.error(f"get_conversation_messages failed | {exc}")
            return []
    def get_llm_context(
        self,
        conversation_id: str,
        limit: int = 10,
    ) -> List[Dict[str, str]]:
        
        messages = self.get_conversation_messages(
            conversation_id=conversation_id,
            limit=limit,
        )
        context = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant")
        ]
        logger.info(
            f" LLM context loaded | conversation={conversation_id} | messages={len(context)}"
        )
        return context

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SAVING MESSAGES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def save_exchange(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        metadata: Dict[str, Any],
        rag_chunks: Optional[List[Dict[str, Any]]] = None,
        skip_save_user: bool = False,
    ) -> Tuple[Optional[str], str]:
       
        rag_chunks = rag_chunks or []

        try:
            # 1. Save user message
            user_msg_id = None
            if not skip_save_user:
                user_msg_id = self._save_single_message(
                    conversation_id=conversation_id,
                    role="user",
                    content=user_message,
                )

            # 2. Normalize sources for storage
            normalized_sources = [
                {
                    "title": chunk.get("file_name") or chunk.get("parent_title") or "Source",
                    "url": chunk.get("url"),
                    "score": chunk.get("score"),
                }
                for chunk in rag_chunks
                if chunk.get("url")
            ]

            # 3. Save assistant message
            assistant_msg_id = self._save_single_message(
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_message,
                sources=normalized_sources,
                metadata=metadata,
            )

            # 4. Save generation metadata
            self._supabase.save_message_metadata(
                message_id=assistant_msg_id,
                model_name=metadata.get("model", settings.AZURE_OPENAI_DEPLOYMENT),
                token_input=metadata.get("token_input", 0),
                token_output=metadata.get("tokens_generated", 0),
                latency_ms=int(metadata.get("query_time", 0) * 1000),
                is_cached=metadata.get("cached", False),
            )

            # 5. Save RAG chunk provenance (LEGAL queries only)
            if rag_chunks:
                self._supabase.save_rag_retrievals(
                    message_id=assistant_msg_id,
                    chunks=rag_chunks,
                )

            logger.info(
                f" Exchange saved | user={user_msg_id} | assistant={assistant_msg_id}"
            )
            return user_msg_id, assistant_msg_id

        except Exception as exc:
            logger.error(f" save_exchange failed | {exc}", exc_info=True)
            raise

    # Keep the old method name as an alias so existing callers don't break
    def save_user_and_assistant_messages(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        metadata: Dict[str, Any],
        rag_chunks: Optional[List[Dict[str, Any]]] = None,
        skip_save_user: bool = False,
    ) -> Tuple[Optional[str], str]:
        """Alias for save_exchange() — preserved for backward compatibility."""
        return self.save_exchange(
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
            metadata=metadata,
            rag_chunks=rag_chunks,
            skip_save_user=skip_save_user,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INTERNAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _save_single_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
       
        message_id = self._supabase.save_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources=sources,
            metadata=metadata,
        )

        # Keep Redis context current
        self._cache.append_message_to_context(
            conversation_id=conversation_id,
            role=role,
            content=content,
            timestamp=datetime.utcnow(),
        )
        self._cache.extend_context_ttl(conversation_id)

        return message_id

    @staticmethod
    def _normalize_sources(raw: List[Any]) -> List[Dict[str, Any]]:
        
        normalized = []
        for chunk in raw:
            if not isinstance(chunk, dict):
                continue
            url = chunk.get("url")
            if not url and chunk.get("chunk_id"):
                url = f"https://lovdata.no/dokument/{chunk['chunk_id']}"
            if url:
                normalized.append({
                    "title": (
                        chunk.get("title")
                        or chunk.get("file_name")
                        or chunk.get("chunk_id")
                        or "Source"
                    ),
                    "url": url,
                })
        return normalized