
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis
from redis.connection import ConnectionPool

logger = logging.getLogger(__name__)


class RedisClient:
    

    _instance: Optional["RedisClient"] = None
    _pool: Optional[ConnectionPool] = None
    _client: Optional[redis.Redis] = None

    def __new__(cls) -> "RedisClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_ready"):
            self._ready = False

    def connect(
        self,
        host: str,
        port: int,
        db: int = 0,
        password: Optional[str] = None,
        max_connections: int = 50,
    ) -> None:
        
        try:
            logger.info(f"🔌 Connecting to Redis at {host}:{port} (DB: {db})...")

            self._pool = ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password or None,
                decode_responses=True,
                max_connections=max_connections,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )

            self._client = redis.Redis(connection_pool=self._pool)
            self._client.ping()

            self._ready = True
            logger.info(f" Redis connected | {host}:{port} | DB: {db}")

        except Exception as exc:
            logger.error(
                f" Redis connection failed | {host}:{port} | {exc}",
                exc_info=True,
            )
            raise ConnectionError(f"Redis connection failed: {exc}") from exc

    # ── Internal helpers ─────────────────────────────────────────────────

    def _get(self) -> redis.Redis:
        if not self._ready or self._client is None:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._client

    def check_connection(self) -> bool:
        """Ping Redis. Returns True when healthy."""
        try:
            self._get().ping()
            return True
        except Exception as exc:
            logger.error(f" Redis health check failed | {exc}")
            return False

    def close(self) -> None:
        """Gracefully close the connection pool."""
        try:
            if self._client:
                self._client.close()
            self._ready = False
            self._client = None
            logger.info(" Redis connection closed")
        except Exception as exc:
            logger.error(f" Error closing Redis: {exc}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONVERSATION CONTEXT  (chat:context:<conversation_id>)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_context(self, conversation_id: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieve cached conversation messages. Returns None on cache miss."""
        try:
            raw = self._get().get(f"chat:context:{conversation_id}")
            if not raw:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.error(f"Redis get_context failed | {exc}")
            return None

    def set_context(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        ttl: int = 1800,
    ) -> bool:
        """Store conversation messages with an expiry (sliding window)."""
        try:
            self._get().setex(
                f"chat:context:{conversation_id}",
                ttl,
                json.dumps(messages, default=str),
            )
            return True
        except Exception as exc:
            logger.error(f"Redis set_context failed | {exc}")
            return False

    def append_message_to_context(
        self,
        conversation_id: str,
        role: str,
        content: str,
        timestamp: Optional[datetime] = None,
        max_messages: int = 20,
        ttl: int = 1800,
    ) -> bool:
        """Append a single message to the cached context list."""
        try:
            messages = self.get_context(conversation_id) or []
            messages.append({
                "role": role,
                "content": content,
                "timestamp": (timestamp or datetime.utcnow()).isoformat(),
            })
            # Keep only the most recent N messages
            if len(messages) > max_messages:
                messages = messages[-max_messages:]
            return self.set_context(conversation_id, messages, ttl)
        except Exception as exc:
            logger.error(f"Redis append_message_to_context failed | {exc}")
            return False

    def extend_context_ttl(self, conversation_id: str, ttl: int = 1800) -> bool:
        """Refresh the TTL on an existing context key (sliding window)."""
        try:
            self._get().expire(f"chat:context:{conversation_id}", ttl)
            return True
        except Exception as exc:
            logger.error(f"Redis extend_context_ttl failed | {exc}")
            return False

    def clear_context(self, conversation_id: str) -> bool:
        """Delete the context key for a conversation."""
        try:
            self._get().delete(f"chat:context:{conversation_id}")
            return True
        except Exception as exc:
            logger.error(f"Redis clear_context failed | {exc}")
            return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONVERSATION METADATA  (conversation:meta:<conversation_id>)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_conversation_meta(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        try:
            raw = self._get().get(f"conversation:meta:{conversation_id}")
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.error(f"Redis get_conversation_meta failed | {exc}")
            return None

    def set_conversation_meta(
        self,
        conversation_id: str,
        metadata: Dict[str, Any],
        ttl: int = 3600,
    ) -> bool:
        try:
            self._get().setex(
                f"conversation:meta:{conversation_id}",
                ttl,
                json.dumps(metadata, default=str),
            )
            return True
        except Exception as exc:
            logger.error(f"Redis set_conversation_meta failed | {exc}")
            return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # USER CONVERSATION LIST  (user:conversations:<user_id>)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_user_conversations(self, user_id: str) -> Optional[List[str]]:
        try:
            raw = self._get().get(f"user:conversations:{user_id}")
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.error(f"Redis get_user_conversations failed | {exc}")
            return None

    def set_user_conversations(
        self,
        user_id: str,
        conversation_ids: List[str],
        ttl: int = 1800,
    ) -> bool:
        try:
            self._get().setex(
                f"user:conversations:{user_id}",
                ttl,
                json.dumps(conversation_ids),
            )
            return True
        except Exception as exc:
            logger.error(f"Redis set_user_conversations failed | {exc}")
            return False

    def add_conversation_to_user(self, user_id: str, conversation_id: str) -> bool:
        """Prepend a conversation ID to the user's list (most recent first)."""
        try:
            ids = self.get_user_conversations(user_id) or []
            if conversation_id not in ids:
                ids.insert(0, conversation_id)
            return self.set_user_conversations(user_id, ids)
        except Exception as exc:
            logger.error(f"Redis add_conversation_to_user failed | {exc}")
            return False

    def clear_all_conversation_cache(self, conversation_id: str) -> bool:
        """Delete all cache keys associated with a conversation."""
        try:
            client = self._get()
            client.delete(f"chat:context:{conversation_id}")
            client.delete(f"conversation:meta:{conversation_id}")
            logger.info(f"  Cleared cache for conversation: {conversation_id}")
            return True
        except Exception as exc:
            logger.error(f"Redis clear_all_conversation_cache failed | {exc}")
            return False


# Module-level singleton and DI factory
redis_client = RedisClient()


def get_redis() -> RedisClient:
    """Return the singleton RedisClient (for dependency injection in main.py)."""
    return redis_client