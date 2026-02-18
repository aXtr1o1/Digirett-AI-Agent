

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import redis
from redis.connection import ConnectionPool

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis client with all caching operations
    Handles conversation context, metadata, sessions, and streaming buffers
    """
    
    _instance: Optional['RedisClient'] = None
    _pool: Optional[ConnectionPool] = None
    _client: Optional[redis.Redis] = None
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize Redis client (called once due to singleton)"""
        if not hasattr(self, 'initialized'):
            self.initialized = False
            logger.info("Redis client instance created")
    
    def connect(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        max_connections: int = 50
    ) -> None:
        """
        Connect to Redis server
        
        Args:
            host: Redis server host
            port: Redis server port
            db: Database number
            password: Optional password
            max_connections: Max connection pool size
            
        Raises:
            ConnectionError: If connection fails
        """
        try:
            logger.info(f"🔌 Connecting to Redis at {host}:{port} (DB: {db})...")
            
            # Create connection pool
            self._pool = ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password if password else None,
                decode_responses=True,  # Auto-decode bytes to strings
                max_connections=max_connections,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True
            )
            
            # Create Redis client
            self._client = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            self._client.ping()
            
            logger.info(
                f"✅ Connected to Redis | "
                f"Host: {host}:{port} | "
                f"DB: {db} | "
                f"Pool size: {max_connections}"
            )
            
            self.initialized = True
            
        except Exception as e:
            logger.error(
                f"❌ Redis connection failed | "
                f"Host: {host}:{port} | "
                f"DB: {db} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            raise ConnectionError(f"Failed to connect to Redis: {str(e)}") from e
    
    def get_client(self) -> redis.Redis:
        """
        Get Redis client instance
        
        Returns:
            redis.Redis client
            
        Raises:
            RuntimeError: If not initialized
        """
        if not self.initialized or self._client is None:
            error_msg = "Redis client not initialized. Call connect() first."
            logger.error(f"❌ {error_msg}")
            raise RuntimeError(error_msg)
        return self._client
    
    def check_connection(self) -> bool:
        """
        Check if Redis connection is alive
        
        Returns:
            bool: True if connected, False otherwise
        """
        try:
            if not self.initialized or self._client is None:
                logger.warning("⚠️  Redis not initialized")
                return False
            
            self._client.ping()
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Redis health check failed | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONVERSATION CONTEXT CACHE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def get_context(self, conversation_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get conversation context from Redis
        
        Args:
            conversation_id: Conversation UUID
            
        Returns:
            List of messages or None if not cached
        """
        try:
            client = self.get_client()
            key = f"chat:context:{conversation_id}"
            data = client.get(key)
            
            if not data:
                logger.debug(f"💨 Context cache miss: {conversation_id}")
                return None
            
            messages = json.loads(data)
            logger.debug(f"✅ Context cache hit: {conversation_id} ({len(messages)} messages)")
            return messages
            
        except Exception as e:
            logger.error(
                f"❌ Failed to get context from Redis | "
                f"Conversation: {conversation_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return None
    
    def set_context(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        ttl: int = 1800
    ) -> bool:
        """
        Save conversation context to Redis
        
        Args:
            conversation_id: Conversation UUID
            messages: List of messages with role, content, timestamp
            ttl: Time to live in seconds (default: 30 min)
            
        Returns:
            bool: True if successful
        """
        try:
            client = self.get_client()
            key = f"chat:context:{conversation_id}"
            data = json.dumps(messages, default=str)
            
            client.setex(key, ttl, data)
            logger.debug(
                f"💾 Context cached: {conversation_id} | "
                f"Messages: {len(messages)} | "
                f"TTL: {ttl}s"
            )
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Failed to set context in Redis | "
                f"Conversation: {conversation_id} | "
                f"Messages: {len(messages)} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    def append_message_to_context(
        self,
        conversation_id: str,
        role: str,
        content: str,
        max_messages: int = 20,
        ttl: int = 1800,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Append new message to conversation context
        
        Args:
            conversation_id: Conversation UUID
            role: "user" or "assistant"
            content: Message content
            max_messages: Keep only last N messages
            ttl: TTL for updated context
            timestamp: Optional timestamp
            
        Returns:
            bool: True if successful
        """
        try:
            # Get current context
            messages = self.get_context(conversation_id) or []
            
            # Add new message
            new_message = {
                "role": role,
                "content": content,
                "timestamp": (timestamp or datetime.utcnow()).isoformat()
            }
            messages.append(new_message)
            
            # Keep only last N messages
            if len(messages) > max_messages:
                messages = messages[-max_messages:]
            
            # Save back
            return self.set_context(conversation_id, messages, ttl)
            
        except Exception as e:
            logger.error(
                f"❌ Failed to append message to context | "
                f"Conversation: {conversation_id} | "
                f"Role: {role} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    def clear_context(self, conversation_id: str) -> bool:
        """Delete conversation context from cache"""
        try:
            client = self.get_client()
            key = f"chat:context:{conversation_id}"
            client.delete(key)
            logger.debug(f"🗑️  Context cleared: {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Failed to clear context | "
                f"Conversation: {conversation_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    def extend_context_ttl(self, conversation_id: str, ttl: int = 1800) -> bool:
        """Extend TTL for conversation context (sliding window)"""
        try:
            client = self.get_client()
            key = f"chat:context:{conversation_id}"
            client.expire(key, ttl)
            logger.debug(f"⏱️  Extended TTL: {conversation_id} → {ttl}s")
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Failed to extend context TTL | "
                f"Conversation: {conversation_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONVERSATION METADATA CACHE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def get_conversation_meta(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation metadata from cache"""
        try:
            client = self.get_client()
            key = f"conversation:meta:{conversation_id}"
            data = client.get(key)
            
            if not data:
                return None
            
            return json.loads(data)
            
        except Exception as e:
            logger.error(
                f"❌ Failed to get conversation meta | "
                f"Conversation: {conversation_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return None
    
    def set_conversation_meta(
        self,
        conversation_id: str,
        metadata: Dict[str, Any],
        ttl: int = 3600
    ) -> bool:
        """Save conversation metadata to cache"""
        try:
            client = self.get_client()
            key = f"conversation:meta:{conversation_id}"
            data = json.dumps(metadata, default=str)
            client.setex(key, ttl, data)
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Failed to set conversation meta | "
                f"Conversation: {conversation_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # USER SESSION & CONVERSATIONS LIST
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def get_user_conversations(self, user_id: str) -> Optional[List[str]]:
        """Get list of user's conversation IDs"""
        try:
            client = self.get_client()
            key = f"user:conversations:{user_id}"
            data = client.get(key)
            
            if not data:
                return None
            
            return json.loads(data)
            
        except Exception as e:
            logger.error(
                f"❌ Failed to get user conversations | "
                f"User: {user_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return None
    
    def set_user_conversations(
        self,
        user_id: str,
        conversation_ids: List[str],
        ttl: int = 1800
    ) -> bool:
        """Save list of user's conversation IDs"""
        try:
            client = self.get_client()
            key = f"user:conversations:{user_id}"
            data = json.dumps(conversation_ids)
            client.setex(key, ttl, data)
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Failed to set user conversations | "
                f"User: {user_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    def add_conversation_to_user(self, user_id: str, conversation_id: str) -> bool:
        """Add conversation ID to user's list (prepend for recent-first)"""
        try:
            conversations = self.get_user_conversations(user_id) or []
            
            if conversation_id not in conversations:
                conversations.insert(0, conversation_id)
            
            return self.set_user_conversations(user_id, conversations)
            
        except Exception as e:
            logger.error(
                f"❌ Failed to add conversation to user | "
                f"User: {user_id} | "
                f"Conversation: {conversation_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # UTILITY METHODS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def clear_all_conversation_cache(self, conversation_id: str) -> bool:
        """Clear all cache entries for a conversation"""
        try:
            client = self.get_client()
            patterns = [
                f"chat:context:{conversation_id}",
                f"conversation:meta:{conversation_id}"
            ]
            
            for pattern in patterns:
                client.delete(pattern)
            
            logger.info(f"🗑️  Cleared all cache for conversation: {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Failed to clear all conversation cache | "
                f"Conversation: {conversation_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    def close(self) -> None:
        """Close Redis connection"""
        try:
            if self._client:
                self._client.close()
                logger.info("🔌 Disconnected from Redis")
            
            self.initialized = False
            self._client = None
            
        except Exception as e:
            logger.error(
                f"❌ Error closing Redis connection | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )


# Global instance
redis_client = RedisClient()


def get_redis() -> RedisClient:
    """
    Get Redis client instance (for dependency injection)
    
    Returns:
        RedisClient instance
    """
    return redis_client