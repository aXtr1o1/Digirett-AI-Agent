"""
startup/database.py — Database & Cache connection initialization
"""

import logging
from typing import Dict, Any, Tuple

from config import settings
from db.milvus_client import get_milvus, MilvusClient
from db.redis_client import get_redis, RedisClient
from db.supabase_client import get_supabase, SupabaseClient

logger = logging.getLogger(__name__)


def init_database_connections() -> Tuple[MilvusClient, RedisClient, SupabaseClient]:
    
    logger.info("Connecting to Milvus...")
    milvus_client = get_milvus()
    milvus_client.connect(
        host=settings.MILVUS_HOST,
        port=settings.MILVUS_PORT,
        collection_name=settings.MILVUS_COLLECTION,
    )

    logger.info("Connecting to Redis...")
    redis_client = get_redis()
    redis_client.connect(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
    )

    logger.info("Connecting to Supabase...")
    supabase_client = get_supabase()
    sb_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
    supabase_client.connect(
        url=settings.SUPABASE_URL,
        key=sb_key,
    )

    return milvus_client, redis_client, supabase_client
