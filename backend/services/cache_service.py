# ============================================
# app/services/cache_service.py
# ============================================

import logging
import redis
import hashlib
import json
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class CacheService:
    """Redis-based caching service"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str = ""
    ):
        """
        Initialize Redis cache
        
        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password
        """
        try:
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password if password else None,
                decode_responses=True,
                socket_connect_timeout=5
            )
            
            # Test connection
            self.redis_client.ping()
            logger.info(f"Redis cache connected: {host}:{port}")
            
        except redis.ConnectionError:
            logger.warning("⚠️  Redis not available, running without cache")
            self.redis_client = None
    
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        if self.redis_client is None:
            return False
        
        try:
            self.redis_client.ping()
            return True
        except:
            return False
    
    def generate_cache_key(self, query: str, top_k: int) -> str:
        """
        Generate cache key from query
        
        Args:
            query: User query
            top_k: Number of results
            
        Returns:
            Cache key (hash)
        """
        # Normalize query
        normalized = query.lower().strip()
        
        # Create hash
        key_string = f"{normalized}:{top_k}"
        hash_key = hashlib.md5(key_string.encode()).hexdigest()
        
        return f"rag:query:{hash_key}"
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached response"""
        if self.redis_client is None:
            return None
        
        try:
            cached = self.redis_client.get(key)
            if cached:
                logger.info(f"Cache HIT: {key}")
                return json.loads(cached)
            
            logger.debug(f"Cache MISS: {key}")
            return None
            
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    def set(self, key: str, value: Dict[str, Any], ttl: int = 3600):
        """
        Set cached response
        
        Args:
            key: Cache key
            value: Response to cache
            ttl: Time to live in seconds
        """
        if self.redis_client is None:
            return
        
        try:
            self.redis_client.setex(
                key,
                ttl,
                json.dumps(value)
            )
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
    
    def delete(self, key: str):
        """Delete cached item"""
        if self.redis_client is None:
            return
        
        try:
            self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
    
    def clear_all(self):
        """Clear all cache"""
        if self.redis_client is None:
            return
        
        try:
            self.redis_client.flushdb()
            logger.info("Cache cleared")
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
    
    def close(self):
        """Close Redis connection"""
        if self.redis_client:
            self.redis_client.close()
            logger.info("Cache connection closed")
