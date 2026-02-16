"""
Azure OpenAI Embedder - TOKEN-AWARE VERSION
Works with token-based chunking (no truncation needed)

Key features:
1. Processes token-bounded chunks safely
2. Batch processing with configurable size
3. Automatic retry on transient errors
4. No text truncation (chunks are already optimally sized)
5. Progress tracking and detailed logging
"""

import logging
import time
from typing import List, Dict, Any

from openai import AzureOpenAI, APIStatusError, APIConnectionError, RateLimitError

from ingestion.src.config import (
    EMBEDDING_CHUNK_DELAY,
    EMBEDDING_BATCH_SIZE,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    EMBEDDING_MODEL,
)


logger = logging.getLogger(__name__)


class TokenAwareAzureEmbedder:
    """
    Embedder for token-bounded chunks.
    Processes chunks in safe batches without truncation.
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: int = 15,
        warn_token_threshold: int = 400
    ):
        """
        Initialize token-aware embedder.

        Args:
            max_retries: Maximum retry attempts on failure
            retry_delay: Seconds to wait before retry
            warn_token_threshold: Log warning if chunk exceeds this token count
        """
        self.deployment = AZURE_OPENAI_DEPLOYMENT
        self.model = EMBEDDING_MODEL
        self.chunk_delay = EMBEDDING_CHUNK_DELAY
        self.batch_size = EMBEDDING_BATCH_SIZE
        self.warn_token_threshold = warn_token_threshold
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self.client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )

        logger.info(
            f"✅ Token-Aware Azure OpenAI Embedder initialized | "
            f"deployment={self.deployment} | "
            f"batch_size={self.batch_size} | chunk_delay={self.chunk_delay}s | "
            f"No truncation (using pre-sized chunks)"
        )

    def _invoke_batch(
        self,
        texts: List[str],
        retry_count: int = 0
    ) -> List[List[float]]:
        """
        Invoke Azure OpenAI embeddings for a BATCH of texts with retry logic.

        Args:
            texts: List of texts to embed (already token-bounded)
            retry_count: Current retry attempt

        Returns:
            List of embeddings (or None for failed items)
        """
        try:
            # Validate inputs
            if not texts or not all(texts):
                logger.warning(f"Empty or invalid texts in batch")
                return [None] * len(texts)

            # Invoke Azure OpenAI embeddings endpoint
            response = self.client.embeddings.create(
                input=texts,
                model=self.deployment,
            )

            # Extract embeddings, sorted by index to match input order
            sorted_data = sorted(response.data, key=lambda item: item.index)
            return [item.embedding for item in sorted_data]

        except (RateLimitError, APIStatusError, APIConnectionError) as e:
            if retry_count < self.max_retries:
                # Exponential backoff
                wait_time = self.retry_delay * (2 ** retry_count)
                logger.warning(
                    f"⚠️  API error on batch of {len(texts)} "
                    f"(attempt {retry_count + 1}/{self.max_retries}). "
                    f"Waiting {wait_time}s..."
                )
                time.sleep(wait_time)
                return self._invoke_batch(texts, retry_count + 1)
            else:
                logger.error(
                    f"❌ Failed after {self.max_retries} retries "
                    f"for batch of {len(texts)}"
                )
                return [None] * len(texts)

        except Exception as e:
            logger.error(f"❌ Invocation failed: {str(e)}")
            return [None] * len(texts)

    def embed_chunks(
        self,
        chunks: List[Dict[str, Any]],
        text_field: str = "text"
    ) -> List[Dict[str, Any]]:
        """
        Embed chunks with token-aware batch processing.

        Strategy:
        1. Process chunks in batches of `batch_size`
        2. Check token counts and warn if oversized
        3. Delay between batches for rate-limit stability
        4. Track progress and success rate

        Args:
            chunks: List of chunk dictionaries
            text_field: Field name containing text

        Returns:
            Chunks with 'embedding' field added
        """
        if not chunks:
            logger.warning("No chunks provided")
            return []

        # Collect valid texts
        texts_to_embed = []
        chunk_indices = []
        oversized_count = 0

        for i, chunk in enumerate(chunks):
            text = chunk.get(text_field, "")
            if text and text.strip():
                # Check token count if available
                token_count = chunk.get("token_count", 0)
                if token_count > self.warn_token_threshold:
                    logger.warning(
                        f"⚠️  Chunk {i} exceeds token threshold: "
                        f"{token_count} > {self.warn_token_threshold} tokens"
                    )
                    oversized_count += 1

                texts_to_embed.append(text)
                chunk_indices.append(i)
            else:
                chunk['embedding'] = None

        if not texts_to_embed:
            logger.error("No valid texts to embed")
            return chunks

        total = len(texts_to_embed)
        estimated_batches = (total + self.batch_size - 1) // self.batch_size
        estimated_time = estimated_batches * (self.chunk_delay + 2.0)  # ~2s per batch

        logger.info(
            f"🧠 Token-aware embedding | chunks={total} | "
            f"batch_size={self.batch_size} | batches={estimated_batches} | "
            f"estimated={estimated_time:.0f}s"
        )

        if oversized_count > 0:
            logger.warning(
                f"   ⚠️  {oversized_count}/{total} chunks exceed token threshold"
            )

        # Process in batches
        embeddings = []
        failed_count = 0

        for batch_idx in range(0, total, self.batch_size):
            batch_end = min(batch_idx + self.batch_size, total)
            batch_texts = texts_to_embed[batch_idx:batch_end]
            batch_num = (batch_idx // self.batch_size) + 1

            logger.info(
                f"   Processing batch {batch_num}/{estimated_batches} "
                f"({len(batch_texts)} chunks)"
            )

            # Get embeddings for batch
            batch_embeddings = self._invoke_batch(batch_texts)

            # Validate results
            if batch_embeddings and len(batch_embeddings) == len(batch_texts):
                embeddings.extend(batch_embeddings)

                # Count failures in batch
                batch_failures = sum(1 for e in batch_embeddings if e is None)
                if batch_failures > 0:
                    failed_count += batch_failures
                    logger.warning(
                        f"   ⚠️  {batch_failures}/{len(batch_texts)} failed in batch"
                    )
            else:
                # Entire batch failed
                logger.error(
                    f"   ❌ Batch {batch_num} failed completely"
                )
                embeddings.extend([None] * len(batch_texts))
                failed_count += len(batch_texts)

                # Stop if too many failures
                if failed_count >= total * 0.5:  # >50% failure rate
                    logger.error(
                        f"❌ Stopping: failure rate too high "
                        f"({failed_count}/{len(embeddings)} failed)"
                    )
                    # Fill remaining with None
                    remaining = total - len(embeddings)
                    if remaining > 0:
                        embeddings.extend([None] * remaining)
                    break

            # Delay between batches (except last one)
            if batch_end < total:
                time.sleep(self.chunk_delay)

            # Log progress every 5 batches
            if batch_num % 5 == 0:
                success = sum(1 for e in embeddings if e is not None)
                logger.info(
                    f"   Progress: {success}/{len(embeddings)} successful so far"
                )

        # Assign embeddings to chunks
        for i, chunk_idx in enumerate(chunk_indices):
            if i < len(embeddings):
                chunks[chunk_idx]['embedding'] = embeddings[i]
            else:
                chunks[chunk_idx]['embedding'] = None

        # Final stats
        successful = sum(1 for e in embeddings if e is not None)
        success_rate = (successful / total * 100) if total > 0 else 0

        logger.info(
            f"✅ Embedded {successful}/{total} chunks ({success_rate:.1f}%)"
        )

        if failed_count > 0:
            logger.warning(f"⚠️  {failed_count} chunks failed")

        return chunks