'''import json
import time
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class SageMakerBGEEmbedder:
    def __init__(
        self,
        endpoint_name: str,
        region_name: str = "ap-south-1",
        max_retries: int = 3,
        retry_delay: int = 20,
        chunk_delay: float = 1.0,
        max_chunks_per_batch: int = 1,   # force SAFE mode
        max_text_length: int = 1000,
        expected_dim: int = 1024,
    ):
        import boto3

        self.endpoint_name = endpoint_name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.chunk_delay = chunk_delay
        self.max_chunks_per_batch = max_chunks_per_batch
        self.max_text_length = max_text_length
        self.expected_dim = expected_dim

        self.client = boto3.client(
            "sagemaker-runtime",
            region_name=region_name
        )

    # -------------------------------------------------
    # Core invocation (single text)
    # -------------------------------------------------
    def _invoke_single(self, text: str, retry_count: int = 0) -> List[float] | None:
        try:
            if len(text) > self.max_text_length:
                text = text[: self.max_text_length]

            payload = {"inputs": [text]}

            response = self.client.invoke_endpoint(
                EndpointName=self.endpoint_name,
                ContentType="application/json",
                Body=json.dumps(payload)
            )

            result = json.loads(response["Body"].read().decode())
            embeddings = self._extract_embeddings(result)

            if embeddings and len(embeddings[0]) == self.expected_dim:
                return embeddings[0]

            logger.error("❌ Invalid embedding shape returned")
            return None

        except Exception as e:
            if retry_count < self.max_retries:
                time.sleep(self.retry_delay * (2 ** retry_count))
                return self._invoke_single(text, retry_count + 1)

            logger.error(f"❌ SageMaker invocation failed: {e}")
            return None

    # -------------------------------------------------
    # Extraction logic (robust)
    # -------------------------------------------------
    def _extract_embeddings(self, result):
        def unwrap(x):
            while isinstance(x, list) and len(x) == 1:
                x = x[0]
            return x

        try:
            if isinstance(result, dict):
                for key in ("embeddings", "outputs", "predictions", "data"):
                    if key in result:
                        result = result[key]
                        break

            result = unwrap(result)

            if isinstance(result, list) and len(result) == self.expected_dim:
                return [result]

            if (
                isinstance(result, list)
                and len(result) > 0
                and isinstance(result[0], list)
                and len(result[0]) == self.expected_dim
            ):
                return result

            logger.error("❌ Unable to extract embeddings")
            return []

        except Exception as e:
            logger.error(f"❌ Embedding extraction failed: {e}")
            return []

    # -------------------------------------------------
    # ✅ PUBLIC API USED BY main.py
    # -------------------------------------------------
    def embed_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generates embeddings for each chunk and injects them back.
        SAFE: one chunk at a time.
        """

        for idx, chunk in enumerate(chunks, 1):
            text = chunk.get("text", "").strip()
            if not text:
                continue

            embedding = self._invoke_single(text)

            if embedding is None:
                raise RuntimeError(f"Embedding failed at chunk {idx}")

            chunk["embedding"] = embedding
            time.sleep(self.chunk_delay)

        return chunks
'''

"""
Token-Aware SageMaker BGE Embedder
Batch processing with safety features and automatic retry logic

Key Features:
1. Batch processing with configurable size
2. Token-aware (works with pre-sized chunks)
3. Automatic retry on failures
4. Progress tracking
5. VRAM-safe processing
"""

import json
import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class SageMakerBGEEmbedder:
    """
    Token-aware SageMaker embedder with batch support
    Matches main.py EXACTLY
    """

    def __init__(
        self,
        endpoint_name: str,
        region_name: str = "ap-south-1",
        batch_size: int = 2,
        chunk_delay: float = 0.5,
        max_retries: int = 3,
        retry_delay: int = 15,
        max_text_length: int = 480,
        expected_dim: int = 1024,
        warn_token_threshold: int = 400,
    ):
        import boto3

        self.endpoint_name = endpoint_name
        self.batch_size = batch_size
        self.chunk_delay = chunk_delay
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.max_text_length = max_text_length
        self.expected_dim = expected_dim
        self.warn_token_threshold = warn_token_threshold

        self.client = boto3.client(
            "sagemaker-runtime",
            region_name=region_name
        )

        logger.info(
            f"✅ Token-Aware SageMaker Embedder initialized | "
            f"batch_size={batch_size} | chunk_delay={chunk_delay}s"
        )

    # -------------------------------------------------
    # Robust extraction
    # -------------------------------------------------
    def _extract_embeddings(self, result: Any) -> List[List[float]]:
        def unwrap(x):
            while isinstance(x, list) and len(x) == 1:
                x = x[0]
            return x

        if isinstance(result, dict):
            for key in ("embeddings", "outputs", "predictions", "data"):
                if key in result:
                    result = result[key]
                    break

        result = unwrap(result)

        if (
            isinstance(result, list)
            and len(result) > 0
            and isinstance(result[0], list)
            and len(result[0]) == self.expected_dim
        ):
            return result

        raise RuntimeError("Invalid embedding response format")

    # -------------------------------------------------
    # Public API used by main.py
    # -------------------------------------------------
    def embed_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        texts = []
        for i, c in enumerate(chunks):
            text = c["text"][: self.max_text_length]
            texts.append(text)

            if len(text.split()) > self.warn_token_threshold:
                logger.warning(
                    f"⚠️  Chunk {i} exceeds token threshold ({self.warn_token_threshold})"
                )

        total = len(texts)
        batches = [
            texts[i : i + self.batch_size]
            for i in range(0, total, self.batch_size)
        ]

        logger.info(
            f"🧠 Embedding | chunks={total} | batch_size={self.batch_size} | batches={len(batches)}"
        )

        all_embeddings = []

        for batch_idx, batch in enumerate(batches, 1):
            for attempt in range(self.max_retries):
                try:
                    response = self.client.invoke_endpoint(
                        EndpointName=self.endpoint_name,
                        ContentType="application/json",
                        Body=json.dumps({"inputs": batch})
                    )

                    result = json.loads(response["Body"].read().decode())
                    embeddings = self._extract_embeddings(result)

                    if len(embeddings) < len(batch):
                        raise RuntimeError(
                        f"Embedding count mismatch: got {len(embeddings)}, expected {len(batch)}"
                    )

                    # If more embeddings returned than requested, trim safely
                    embeddings = embeddings[:len(batch)]

                    all_embeddings.extend(embeddings)
                    break

                except Exception as e:
                    if attempt + 1 == self.max_retries:
                        raise
                    wait = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"⚠️ Batch {batch_idx} failed (attempt {attempt+1}), retrying in {wait}s"
                    )
                    time.sleep(wait)

            time.sleep(self.chunk_delay)

        for i, chunk in enumerate(chunks):
            chunk["embedding"] = all_embeddings[i]

        return chunks

if __name__ == "__main__":
    # Example usage
    embedder = SageMakerBGEEmbedder(
        endpoint_name="embedding-bge-m3-endpoint",
        region_name="ap-south-1",
        batch_size=4,
        chunk_delay=0.5
    )
    
    print("✅ Token-aware embedder ready")