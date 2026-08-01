import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4, UUID

from supabase import create_client, Client, ClientOptions
import httpx

logger = logging.getLogger(__name__)


class SupabaseClient:
    

    _instance: Optional["SupabaseClient"] = None
    _client: Optional[Client] = None

    def __new__(cls) -> "SupabaseClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_ready"):
            self._ready = False

    def connect(self, url: str, key: str) -> None:
        
        try:
            logger.info(f"Connecting to Supabase at {url[:40]}...")
            
            # Configure custom httpx.Client with http2=False to prevent connection drops/Server disconnected errors
            http_client = httpx.Client(
                http2=False,
                limits=httpx.Limits(
                    max_keepalive_connections=20,
                    max_connections=100,
                    keepalive_expiry=30.0
                ),
                timeout=httpx.Timeout(60.0, connect=30.0),  # Increase connect timeout to 30s to allow handshake under load
                trust_env=False  # Speed up handshake by bypassing system proxy scanning
            )
            options = ClientOptions(httpx_client=http_client)
            
            self._client = create_client(url, key, options=options)

            # Smoke-test: query the users table
            smoke_query = self._client.table("users").select("user_id").limit(1)
            self.execute_query(smoke_query)

            self._ready = True
            logger.info("Supabase connected")

        except Exception as exc:
            logger.error(f"[ERROR] Supabase connection failed | {exc}", exc_info=True)
            raise ConnectionError(f"Supabase connection failed: {exc}") from exc

    # ── Internal helpers ─────────────────────────────────────────────────

    def _get(self) -> Client:
        if not self._ready or self._client is None:
            raise RuntimeError("Supabase not connected. Call connect() first.")
        return self._client

    def table(self, name: str):
        """Proxy to the underlying supabase-py table builder."""
        return self._get().table(name)

    def check_connection(self) -> bool:
        """Quick health check — returns True when reachable."""
        try:
            self._get().table("users").select("user_id").limit(1).execute()
            return True
        except Exception as exc:
            logger.error(f"[ERROR] Supabase health check failed | {exc}")
            return False

    def execute_query(self, query, max_retries: int = 3):
        import time
        import random
        import httpx
        last_exc = None
        for attempt in range(max_retries):
            try:
                return query.execute()
            except (httpx.HTTPError, Exception) as exc:
                last_exc = exc
                backoff = (0.2 * (2 ** attempt)) + random.uniform(0.05, 0.25)
                logger.warning(
                    f"[WARN] Supabase retry attempt {attempt+1}/{max_retries} after {backoff:.2f}s | {exc}"
                )
                time.sleep(backoff)
        raise last_exc

    def rpc(self, fn_name: str, params: Optional[Dict[str, Any]] = None):
        """Execute a PostgreSQL Remote Procedure Call (RPC) function transactionally."""
        return self._get().rpc(fn_name, params or {})


    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONVERSATIONS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def create_conversation(
        self,
        user_id: str,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
       
        try:
            now = datetime.utcnow().isoformat()
            conversation_id = str(uuid4())

            response = self._get().table("conversations").insert({
                "conversation_id": conversation_id,
                "user_id": user_id,
                "title": title or "New conversation",
                "created_at": now,
                "updated_at": now,
            }).execute()

            conversation = response.data[0]
            logger.info(f" Created conversation {conversation_id} for user {user_id}")
            return conversation

        except Exception as exc:
            logger.error(f" create_conversation failed | {exc}", exc_info=True)
            raise ValueError(f"Failed to create conversation: {exc}") from exc

    def update_conversation_title(
        self,
        conversation_id: str,
        title: str,
    ) -> bool:
        """Update the title of an existing conversation."""
        try:
            self._get().table("conversations").update({
                "title": title,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("conversation_id", conversation_id).execute()

            logger.info(f" Updated title for conversation {conversation_id}")
            return True

        except Exception as exc:
            logger.error(f" update_conversation_title failed | {exc}")
            return False

    def update_conversation_summary(
        self,
        conversation_id: str,
        summary: str,
    ) -> bool:
        """Update the conversation_summary column for a conversation."""
        try:
            self._get().table("conversations").update({
                "conversation_summary": summary,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("conversation_id", conversation_id).execute()

            logger.info(f"[OK] Updated summary for conversation {conversation_id}")
            return True

        except Exception as exc:
            logger.error(f"❌ update_conversation_summary failed | {exc}")
            return False

    def soft_delete_conversation(self, conversation_id: str) -> bool:
        """Mark a conversation (and its messages) as deleted without removing rows."""
        try:
            now = datetime.utcnow().isoformat()
            self._get().table("conversations").update({
                "is_deleted": True,
                "deleted_at": now,
            }).eq("conversation_id", conversation_id).execute()

            self._get().table("messages").update({
                "is_deleted": True,
                "deleted_at": now,
            }).eq("conversation_id", conversation_id).execute()

            logger.info(f" Soft-deleted conversation {conversation_id}")
            return True

        except Exception as exc:
            logger.error(f" soft_delete_conversation failed | {exc}")
            return False

    def get_conversation_by_id(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Fetch active (non-deleted) conversation record by ID."""
        try:
            resp = self.execute_query(
                self._get().table("conversations")
                .select("*")
                .eq("conversation_id", conversation_id)
                .eq("is_deleted", False)
            )
            return resp.data[0] if resp.data else None
        except Exception as exc:
            logger.error(f"❌ get_conversation_by_id failed | {exc}")
            return None

    def touch_conversation(self, conversation_id: str) -> bool:
        """Touch updated_at timestamp on a conversation."""
        try:
            now = datetime.utcnow().isoformat()
            self.execute_query(
                self._get().table("conversations")
                .update({"updated_at": now})
                .eq("conversation_id", conversation_id)
            )
            return True
        except Exception as exc:
            logger.error(f"❌ touch_conversation failed | {exc}")
            return False

    def save_case_brief(self, ticket_id: str, brief_data: Dict[str, Any]) -> bool:
        """Store AI case brief on a HITL ticket."""
        try:
            self.execute_query(
                self._get().table("hitl_tickets")
                .update({"ai_brief": brief_data})
                .eq("ticket_id", ticket_id)
            )
            return True
        except Exception as exc:
            logger.error(f"❌ save_case_brief failed for ticket {ticket_id} | {exc}")
            return False

    def get_document_by_id(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Fetch user library document by ID."""
        try:
            resp = self.execute_query(
                self._get().table("user_library_documents")
                .select("*")
                .eq("id", document_id)
            )
            return resp.data[0] if resp.data else None
        except Exception as exc:
            logger.error(f"❌ get_document_by_id failed for {document_id} | {exc}")
            return None


    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MESSAGES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _deduplicate_sources(
        self,
        sources: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Ensure unique URLs inside sources array to satisfy DB constraint.
        """
        if not sources:
            return sources

        seen = set()
        unique_sources = []

        for src in sources:
            url = src.get("url")
            if not url:
                continue
            if url not in seen:
                seen.add(url)
                unique_sources.append(src)

        return unique_sources

    def _sanitize_for_json(self, data: Any) -> Any:
        """Recursively convert UUID objects (and non-serializable objects) to strings."""
        if isinstance(data, UUID):
            return str(data)
        elif isinstance(data, dict):
            return {k: self._sanitize_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._sanitize_for_json(item) for item in data]
        return data

    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        
        try:
            message_id = str(uuid4())
            now = datetime.utcnow().isoformat()
            clean_sources = None
            if role == "assistant" and sources:
                clean_sources = self._deduplicate_sources(sources)
            
            clean_sources = self._sanitize_for_json(clean_sources)
            clean_metadata = self._sanitize_for_json(metadata)

            query = self._get().table("messages").insert({
                "message_id": message_id,
                "conversation_id": str(conversation_id),
                "role": role,
                "content": content,
                "sources": clean_sources,
                "metadata": clean_metadata,
                "created_at": now,
            })
            self.execute_query(query)

            # Keep conversation updated_at current
            update_query = self._get().table("conversations").update({
                "updated_at": now,
            }).eq("conversation_id", conversation_id)
            self.execute_query(update_query)

            logger.debug(f" Saved {role} message {message_id}")
            return message_id

        except Exception as exc:
            logger.error(f" save_message failed | {exc}", exc_info=True)
            raise ValueError(f"Failed to save message: {exc}") from exc

    def save_message_metadata(
        self,
        message_id: str,
        model_name: str,
        token_input: int,
        token_output: int,
        latency_ms: int,
        is_cached: bool = False,
    ) -> bool:
        """Insert a row into message_metadata."""
        try:
            query = self._get().table("message_metadata").insert({
                "message_id": message_id,
                "model_name": model_name,
                "token_input": token_input,
                "token_output": token_output,
                "latency_ms": latency_ms,
                "is_cached": is_cached,
                "created_at": datetime.utcnow().isoformat(),
            })
            self.execute_query(query)
            return True
        except Exception as exc:
            logger.error(f" save_message_metadata failed | {exc}")
            return False

    def save_rag_retrievals(
        self,
        message_id: str,
        chunks: List[Dict[str, Any]],
    ) -> bool:
        """Batch-insert RAG chunk provenance into rag_retrievals."""
        try:
            rows = [
                {
                    "message_id": message_id,
                    "chunk_id": chunk.get("chunk_id") or chunk.get("file_name") or "unknown",
                    "similarity_score": chunk.get("score", 0.0),
                    "rank": idx,
                    "created_at": datetime.utcnow().isoformat(),
                    "source_title": chunk.get("_resolved_title"),
                }
                for idx, chunk in enumerate(chunks, start=1)
            ]
            if not rows:
                return True

            query = self._get().table("rag_retrievals").insert(rows)
            self.execute_query(query)
            logger.debug(f"[OK] Saved {len(rows)} RAG retrievals for message {message_id}")
            return True
        except Exception as exc:
            logger.error(f" save_rag_retrievals failed | {exc}")
            return False


# Module-level singleton and DI factory
supabase_client = SupabaseClient()


def get_supabase() -> SupabaseClient:
    """Return the singleton SupabaseClient (for dependency injection in main.py)."""
    return supabase_client