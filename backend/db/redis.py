import hashlib
import json
import logging
from typing import Optional

import redis

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self, redis_url: str):
        self.client = None
        if not redis_url:
            logger.info("Redis disabled: REDIS_URL not set")
            return
        self.client = redis.from_url(redis_url, decode_responses=True)

    def is_connected(self) -> bool:
        try:
            return bool(self.client and self.client.ping())
        except Exception:
            return False

    def generate_key(
        self,
        query: str,
        top_k: int,
        prompt_version: str,
        collection: str,
        embed_deployment: str,
        chat_deployment: str,
        include_sources: bool,
        temperature: float,
    ) -> str:
        raw = (
            f"{prompt_version}::{collection}::{embed_deployment}::{chat_deployment}"
            f"::{top_k}::{include_sources}::{temperature}::{(query or '').strip()}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[dict]:
        if not self.client:
            return None
        try:
            v = self.client.get(key)
            return json.loads(v) if v else None
        except Exception as e:
            logger.info(f"Redis get failed: {type(e).__name__}")
            return None

    def set(self, key: str, value: dict, ttl: int):
        if not self.client:
            return
        try:
            self.client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        except Exception as e:
            logger.info(f"Redis set failed: {type(e).__name__}")

    def close(self):
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
