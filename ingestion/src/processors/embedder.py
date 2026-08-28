import logging
import time
from typing import Any, Dict, List, Optional

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    _PSUTIL_AVAILABLE = False

from openai import APIConnectionError, APIStatusError, AzureOpenAI, RateLimitError

from ingestion.src.config import (
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    EMBED_CPU_PAUSE_SECS,
    EMBED_CPU_PAUSE_THRESHOLD,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_CHUNK_DELAY,
    EMBEDDING_MODEL,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_RETRY_DELAY,
)

logger = logging.getLogger(__name__)

# Must match SectionSplitter.EMBED_HARD_CAP in chunker.py
_EMBED_HARD_CAP = 8_000


class TokenAwareAzureEmbedder:
    """Embeds token-bounded chunks with CPU-aware batch pacing."""

    def __init__(
        self,
        max_retries:          int = EMBEDDING_MAX_RETRIES,
        retry_delay:          int = EMBEDDING_RETRY_DELAY,
        warn_token_threshold: int = 400,
    ) -> None:
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
            timeout=15.0,
            max_retries=0,
        )

        logger.info(
            f"Embedder ready | deployment={self.deployment} | "
            f"batch={self.batch_size} | delay={self.chunk_delay}s | "
            f"cpu-pause-at={EMBED_CPU_PAUSE_THRESHOLD}%"
        )
    def _maybe_pause_for_cpu(self) -> None:
        if not _PSUTIL_AVAILABLE or psutil is None:
            return
        try:
            cpu = psutil.cpu_percent(interval=None)
            if cpu >= EMBED_CPU_PAUSE_THRESHOLD:
                logger.warning(
                    f"Embedder: CPU={cpu}% >= {EMBED_CPU_PAUSE_THRESHOLD}% "
                    f"— pausing {EMBED_CPU_PAUSE_SECS}s"
                )
                time.sleep(EMBED_CPU_PAUSE_SECS)
        except Exception:
            pass

    def _wait_for_network_recovery(self, check_interval: float = 10.0) -> None:
        """Pauses execution and probes network connectivity until Wi-Fi / Internet is restored."""
        logger.warning("⚠️ [NETWORK OFFLINE] Azure OpenAI connection lost. Pausing embeddings. Waiting for Wi-Fi reconnection...")
        import socket
        while True:
            time.sleep(check_interval)
            # 1. Fast DNS socket probe (no SSL handshake issues)
            is_online = False
            for host, port in [("8.8.8.8", 53), ("1.1.1.1", 53)]:
                try:
                    with socket.create_connection((host, port), timeout=4.0):
                        is_online = True
                        break
                except OSError:
                    pass

            if is_online:
                logger.info("✅ [NETWORK RESTORED] Internet connection re-established. Resuming Azure OpenAI embeddings...")
                # Re-initialize AzureOpenAI client to reset stale connection pool
                self.client = AzureOpenAI(
                    azure_endpoint=AZURE_OPENAI_ENDPOINT,
                    api_key=AZURE_OPENAI_KEY,
                    api_version=AZURE_OPENAI_API_VERSION,
                    timeout=15.0,
                    max_retries=0,
                )
                return
            logger.warning("⏳ [WAITING FOR WI-FI] Still disconnected. Retrying in %ds...", int(check_interval))

    def _invoke_batch(
        self,
        texts:       List[str],
        retry_count: int = 0,
    ) -> List[Optional[List[float]]]:

        if not texts or not all(texts):
            return [None] * len(texts)

        try:
            response    = self.client.embeddings.create(input=texts, model=self.deployment)
            sorted_data = sorted(response.data, key=lambda item: item.index)
            return [item.embedding for item in sorted_data]

        except APIStatusError as exc:
            status = (
                getattr(exc, "status_code", None)
                or getattr(getattr(exc, "response", None), "status_code", None)
            )
            if status == 400:
                logger.error("400 model_error (likely input too long). Not retrying.")
                return [None] * len(texts)
            return self._retry(texts, retry_count, f"HTTP {status}")

        except RateLimitError:
            return self._retry(texts, retry_count, "429 rate limit")

        except APIConnectionError as conn_err:
            logger.warning("⚠️ Azure OpenAI APIConnectionError: %s", conn_err)
            self._wait_for_network_recovery()
            return self._invoke_batch(texts, retry_count)

        except Exception as exc:
            logger.error(f"Invocation failed: {exc}")
            return [None] * len(texts)

    def _retry(
        self,
        texts:       List[str],
        retry_count: int,
        reason:      str,
    ) -> List[Optional[List[float]]]:
        if retry_count < self.max_retries:
            wait = self.retry_delay * (2 ** retry_count)
            logger.warning(
                f"  {reason} (attempt {retry_count + 1}/{self.max_retries}) "
                f"— waiting {wait}s"
            )
            time.sleep(wait)
            return self._invoke_batch(texts, retry_count + 1)
        logger.error(f"  Failed after {self.max_retries} retries ({reason})")
        return [None] * len(texts)
    def embed_chunks(
        self,
        chunks:     List[Dict[str, Any]],
        text_field: str = "text",
    ) -> List[Dict[str, Any]]:
        if not chunks:
            logger.warning("No chunks provided to embed")
            return []

        texts_to_embed: List[str] = []
        chunk_indices:  List[int] = []
        oversized_count = 0

        for i, chunk in enumerate(chunks):
            text = chunk.get(text_field, "")
            tok  = chunk.get("token_count", 0) or 0

            if tok > _EMBED_HARD_CAP:
                logger.error(
                    f"Oversized chunk blocked: idx={i} tokens={tok} (cap={_EMBED_HARD_CAP})"
                )
                chunk["embedding"] = None
                continue

            if text and text.strip():
                if tok > self.warn_token_threshold:
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
            f"Embedding {total} chunk(s) | "
            f"batches={estimated_batches} | est={estimated_time:.0f}s"
        )
        if oversized_count:
            logger.warning(f"  {oversized_count}/{total} exceed warn threshold")

        embeddings:  List[Optional[List[float]]] = []
        failed_count = 0

        for batch_start in range(0, total, self.batch_size):
            batch_end   = min(batch_start + self.batch_size, total)
            batch_texts = texts_to_embed[batch_start:batch_end]
            batch_num   = batch_start // self.batch_size + 1

            self._maybe_pause_for_cpu()
            logger.info(f"  Batch {batch_num}/{estimated_batches} ({len(batch_texts)} chunks)")

            batch_embeddings = self._invoke_batch(batch_texts)

            if batch_embeddings and len(batch_embeddings) == len(batch_texts):
                embeddings.extend(batch_embeddings)
                batch_failures = sum(1 for e in batch_embeddings if e is None)
                if batch_failures:
                    failed_count += batch_failures
                    logger.warning(f"  {batch_failures}/{len(batch_texts)} failed in batch")
            else:
                logger.error(f"  Batch {batch_num} failed completely")
                embeddings.extend([None] * len(batch_texts))
                failed_count += len(batch_texts)

                if failed_count >= total * 0.5:
                    logger.error(
                        f"Stopping: failure rate too high "
                        f"({failed_count}/{len(embeddings)})"
                    )
                    remaining = total - len(embeddings)
                    if remaining > 0:
                        embeddings.extend([None] * remaining)
                    break

            if batch_end < total:
                time.sleep(self.chunk_delay)

            if batch_num % 5 == 0:
                ok = sum(1 for e in embeddings if e is not None)
                logger.info(f"  Progress: {ok}/{len(embeddings)} successful")

        for i, chunk_idx in enumerate(chunk_indices):
            chunks[chunk_idx]["embedding"] = (
                embeddings[i] if i < len(embeddings) else None
            )

        successful   = sum(1 for e in embeddings if e is not None)
        success_rate = successful / total * 100 if total > 0 else 0
        logger.info(f"Embedded {successful}/{total} ({success_rate:.1f}%)")
        if failed_count:
            logger.warning(f"  {failed_count} chunk(s) failed to embed")

        return chunks