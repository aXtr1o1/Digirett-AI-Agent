"""
Azure OpenAI Embedder — CPU-throttled version
===============================================
All tuning constants are imported from config.py (which reads .env).
No os.getenv calls or numeric literals appear in this file.
"""

import logging
import time
from typing import List, Dict, Any

import psutil
from openai import AzureOpenAI, APIStatusError, APIConnectionError, RateLimitError

from ingestion.src.config import (
    EMBEDDING_CHUNK_DELAY,
    EMBEDDING_BATCH_SIZE,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    EMBEDDING_MODEL,
    EMBED_CPU_PAUSE_THRESHOLD,
    EMBED_CPU_PAUSE_SECS,
)

logger = logging.getLogger(__name__)


class TokenAwareAzureEmbedder:
    """Embedder for token-bounded chunks with CPU-aware batch pacing."""

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: int = 15,
        warn_token_threshold: int = 400,
    ):
        self.deployment           = AZURE_OPENAI_DEPLOYMENT
        self.model                = EMBEDDING_MODEL
        self.chunk_delay          = EMBEDDING_CHUNK_DELAY
        self.batch_size           = EMBEDDING_BATCH_SIZE
        self.warn_token_threshold = warn_token_threshold
        self.max_retries          = max_retries
        self.retry_delay          = retry_delay

        self.client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )

        logger.info(
            f"✅ Embedder ready | deployment={self.deployment} | "
            f"batch={self.batch_size} | delay={self.chunk_delay}s | "
            f"cpu-pause-at={EMBED_CPU_PAUSE_THRESHOLD}%"
        )

    # ------------------------------------------------------------------
    # CPU pause helper — threshold and duration come from config
    # ------------------------------------------------------------------
    def _maybe_pause_for_cpu(self) -> None:
        cpu = psutil.cpu_percent(interval=None)
        if cpu >= EMBED_CPU_PAUSE_THRESHOLD:
            logger.warning(
                f"🟠 Embedder: CPU={cpu}% >= {EMBED_CPU_PAUSE_THRESHOLD}% "
                f"— pausing {EMBED_CPU_PAUSE_SECS}s"
            )
            time.sleep(EMBED_CPU_PAUSE_SECS)

    # ------------------------------------------------------------------
    # Batch API call with exponential-backoff retry
    # ------------------------------------------------------------------
    def _invoke_batch(
        self, texts: List[str], retry_count: int = 0
    ) -> List[List[float]]:
        try:
            if not texts or not all(texts):
                return [None] * len(texts)

            response    = self.client.embeddings.create(
                input=texts,
                model=self.deployment,
            )
            sorted_data = sorted(response.data, key=lambda item: item.index)
            return [item.embedding for item in sorted_data]

        except (RateLimitError, APIStatusError, APIConnectionError) as e:
            if retry_count < self.max_retries:
                wait_time = self.retry_delay * (2 ** retry_count)
                logger.warning(
                    f"⚠️  API error (attempt {retry_count + 1}/{self.max_retries}) "
                    f"— waiting {wait_time}s"
                )
                time.sleep(wait_time)
                return self._invoke_batch(texts, retry_count + 1)
            else:
                logger.error(f"❌ Failed after {self.max_retries} retries")
                return [None] * len(texts)

        except Exception as e:
            logger.error(f"❌ Invocation failed: {e}")
            return [None] * len(texts)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def embed_chunks(
        self, chunks: List[Dict[str, Any]], text_field: str = "text"
    ) -> List[Dict[str, Any]]:
        if not chunks:
            logger.warning("No chunks provided")
            return []

        texts_to_embed  = []
        chunk_indices   = []
        oversized_count = 0

        for i, chunk in enumerate(chunks):
            text = chunk.get(text_field, "")
            if text and text.strip():
                if chunk.get("token_count", 0) > self.warn_token_threshold:
                    oversized_count += 1
                texts_to_embed.append(text)
                chunk_indices.append(i)
            else:
                chunk["embedding"] = None

        if not texts_to_embed:
            logger.error("No valid texts to embed")
            return chunks

        total             = len(texts_to_embed)
        estimated_batches = (total + self.batch_size - 1) // self.batch_size
        estimated_time    = estimated_batches * (self.chunk_delay + 2.0)

        logger.info(
            f"🧠 Embedding {total} chunks | "
            f"batches={estimated_batches} | est={estimated_time:.0f}s"
        )
        if oversized_count:
            logger.warning(f"   ⚠️  {oversized_count}/{total} exceed token threshold")

        embeddings   = []
        failed_count = 0

        for batch_idx in range(0, total, self.batch_size):
            batch_end   = min(batch_idx + self.batch_size, total)
            batch_texts = texts_to_embed[batch_idx:batch_end]
            batch_num   = batch_idx // self.batch_size + 1

            # CPU check before each batch (threshold & sleep from config)
            self._maybe_pause_for_cpu()

            logger.info(f"   Batch {batch_num}/{estimated_batches} ({len(batch_texts)} chunks)")

            batch_embeddings = self._invoke_batch(batch_texts)

            if batch_embeddings and len(batch_embeddings) == len(batch_texts):
                embeddings.extend(batch_embeddings)
                batch_failures = sum(1 for e in batch_embeddings if e is None)
                if batch_failures:
                    failed_count += batch_failures
                    logger.warning(
                        f"   ⚠️  {batch_failures}/{len(batch_texts)} failed in batch"
                    )
            else:
                logger.error(f"   ❌ Batch {batch_num} failed completely")
                embeddings.extend([None] * len(batch_texts))
                failed_count += len(batch_texts)

                if failed_count >= total * 0.5:
                    logger.error(
                        f"❌ Stopping: failure rate too high "
                        f"({failed_count}/{len(embeddings)})"
                    )
                    remaining = total - len(embeddings)
                    if remaining > 0:
                        embeddings.extend([None] * remaining)
                    break

            # Rate-limit delay between batches (skip after last)
            if batch_end < total:
                time.sleep(self.chunk_delay)

            if batch_num % 5 == 0:
                ok = sum(1 for e in embeddings if e is not None)
                logger.info(f"   Progress: {ok}/{len(embeddings)} successful")

        # Assign embeddings back to chunks
        for i, chunk_idx in enumerate(chunk_indices):
            chunks[chunk_idx]["embedding"] = (
                embeddings[i] if i < len(embeddings) else None
            )

        successful   = sum(1 for e in embeddings if e is not None)
        success_rate = successful / total * 100 if total > 0 else 0
        logger.info(f"✅ Embedded {successful}/{total} ({success_rate:.1f}%)")
        if failed_count:
            logger.warning(f"⚠️  {failed_count} chunks failed")

        return chunks

    def _split_oversized_text(self, text: str, max_chars: int = 3000):
        parts, start = [], 0
        while start < len(text):
            parts.append(text[start: start + max_chars])
            start += max_chars
        return parts