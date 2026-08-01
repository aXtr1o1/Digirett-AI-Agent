"""
services/title_translation_service.py — Lovdata Citation Title Translation Service

Handles legal document title translation from Norwegian into target user languages.
Uses a 2-layer cache:
  L1 Redis : per-URL lookup (TTL 7 days)
  L2 LLM   : batched single LLM call for cache misses, back-filling L1 Redis
"""

import logging
import re
from typing import Any, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

_TRANSLATED_TTL = 604_800  # 7 days


class TitleTranslationService:

    def __init__(self, llm_service, message_service) -> None:
        self._llm_service = llm_service
        self._message_service = message_service
        logger.info("[OK] TitleTranslationService initialized")

    def _redis_translated_key(self, lang_key: str, url: str) -> str:
        return f"lovdata_title_translated:{lang_key}:{url}"

    def _redis_get_translated(self, redis_client, lang_key: str, url: str) -> Optional[str]:
        if not redis_client or not url:
            return None
        try:
            val = redis_client._client.get(self._redis_translated_key(lang_key, url))
            return val if isinstance(val, str) else (val.decode() if val else None)
        except Exception:
            return None

    def _redis_set_translated(self, redis_client, lang_key: str, url: str, title: str) -> None:
        if not redis_client or not url:
            return
        try:
            redis_client._client.setex(self._redis_translated_key(lang_key, url), _TRANSLATED_TTL, title)
        except Exception:
            pass

    async def translate_titles(
        self,
        titles: List[str],
        language: str,
        urls: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Translates Norwegian legal titles to `language`.
        Returns original titles on error or if language is Norwegian.
        """
        if not titles:
            return titles

        if language.lower() in ("norwegian", "norsk", "nb", "no"):
            logger.debug("🌐 Citation titles: language=norwegian — skipping translation")
            return titles

        redis_client = self._message_service.get_cache()
        llm = self._llm_service.get_llm_client()
        lang_key = language.lower().replace(" ", "_")

        try:
            result = list(titles)
            need_llm_idx: List[int] = []
            need_llm_titles: List[str] = []

            for i, (title, url) in enumerate(zip(titles, (urls or [None] * len(titles)))):
                cached = self._redis_get_translated(redis_client, lang_key, url) if url else None
                if cached:
                    result[i] = cached
                    logger.debug(f"🌐 Redis hit translated | {url} → '{cached[:60]}'")
                else:
                    need_llm_idx.append(i)
                    need_llm_titles.append(title)

            if not need_llm_titles:
                logger.info(f"🌐 All {len(titles)} titles served from Redis cache | lang={language}")
                return result

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

            messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            response = await llm.agenerate([messages])
            raw_output = response.generations[0][0].text.strip()

            translated_batch: List[str] = []
            for line in raw_output.splitlines():
                line = line.strip()
                if not line:
                    continue
                cleaned = re.sub(r"^\d+\.\s*", "", line).strip()
                if cleaned:
                    translated_batch.append(cleaned)

            if len(translated_batch) != len(need_llm_titles):
                logger.warning(
                    f"⚠️ Citation translation returned {len(translated_batch)} items "
                    f"for {len(need_llm_titles)} titles — using originals for missed"
                )
                for j, orig_idx in enumerate(need_llm_idx):
                    if j < len(translated_batch):
                        result[orig_idx] = translated_batch[j]
                return result

            for j, orig_idx in enumerate(need_llm_idx):
                translated = translated_batch[j]
                result[orig_idx] = translated
                url = (urls or [None] * len(titles))[orig_idx]
                if url:
                    self._redis_set_translated(redis_client, lang_key, url, translated)
                    logger.debug(f"🌐 Redis store translated | {url} → '{translated[:60]}'")

            logger.info(
                f"🌐 Citation titles translated to '{language}' | "
                f"llm={len(need_llm_titles)} | cache_hit={len(titles) - len(need_llm_idx)}"
            )
            return result

        except Exception as exc:
            logger.warning(f"⚠️ Citation title translation failed (non-fatal) | {exc}")
            return titles
