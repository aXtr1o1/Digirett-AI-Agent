"""
app/services/embedding_service.py
AWS SageMaker BGE-M3 Embedding Service (PRODUCTION VERSION)

Replaces local FlagEmbedding with deployed SageMaker endpoint
✅ No version conflicts
✅ No local model loading
✅ Production-ready with retry logic
"""

import logging
import json
import time
import boto3
from typing import List
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    AWS SageMaker BGE-M3 Embedding Service
    
    Uses deployed SageMaker endpoint instead of local models
    This avoids FlagEmbedding/torch version conflicts
    """
    
    def __init__(
        self,
        endpoint_name: str = "embedding-bge-m3-endpoint",
        region_name: str = "ap-south-1",
        batch_size: int = 16,
        max_retries: int = 3,
        retry_delay: int = 5
    ):
        """
        Initialize SageMaker embedding service
        
        Args:
            endpoint_name: SageMaker endpoint name
            region_name: AWS region
            batch_size: Texts per batch (reduce if worker crashes)
            max_retries: Number of retries for failed requests
            retry_delay: Seconds to wait between retries
        """
        self.endpoint_name = endpoint_name
        self.region_name = region_name
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.dimension = 1024  # BGE-M3 embedding dimension
        
        # Initialize AWS SageMaker Runtime client
        try:
            self.client = boto3.client(
                "sagemaker-runtime",
                region_name=settings.AWS_DEFAULT_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )
            logger.info(
                f"✅ SageMaker BGE-M3 Embedder initialized | "
                f"endpoint={endpoint_name} | region={region_name} | batch_size={batch_size}"
            )
        except Exception as e:
            logger.error(f"❌ Failed to initialize SageMaker client: {e}")
            raise
    def _normalize_embeddings(self, result) -> List[List[float]]:
        """
        Normalize SageMaker output to List[List[float]]
        Ensures shape: (batch_size, 1024)
        """

        # Step 1: flatten excessive nesting
        while isinstance(result, list) and len(result) == 1:
            result = result[0]

        # Step 2: now result should be either:
        # - List[List[float]]
        # - List[List[List[float]]]

        normalized = []

        for item in result:
            # Case: [[[float]]] → unwrap
            while isinstance(item, list) and len(item) == 1 and isinstance(item[0], list):
                item = item[0]

            # Final validation
            if not isinstance(item, list) or not item or not isinstance(item[0], (int, float)):
                raise ValueError(f"Invalid embedding structure: {item}")

            normalized.append(item)

        return normalized

    def _invoke_endpoint(self, texts: List[str], retry_count: int = 0) -> List[List[float]]:
        """
        Invoke SageMaker endpoint with retry logic
        
        Handles "Worker died" errors gracefully
        
        Args:
            texts: List of text strings to embed
            retry_count: Current retry attempt
            
        Returns:
            List of 1024-dimensional embeddings
        """
        try:
            payload = {"inputs": texts}
            
            response = self.client.invoke_endpoint(
                EndpointName=self.endpoint_name,
                ContentType="application/json",
                Body=json.dumps(payload)
            )
            
            result = json.loads(response["Body"].read().decode())
            
            # ✅ FIX: Your endpoint returns [[[[embedding]]]] (4 levels of nesting!)
            # We need to unwrap the layers to get List[List[float]]
            
            # Unwrap nested lists until we get to the actual embeddings
            embeddings = self._normalize_embeddings(result)

            # Final safety check
            for emb in embeddings:
                if len(emb) != self.dimension:
                    raise ValueError(
                        f"Embedding dimension mismatch: expected {self.dimension}, got {len(emb)}"
                    )

            logger.debug(
                f"Extracted {len(embeddings)} embeddings, dimension: {len(embeddings[0])}"
            )

            return embeddings

            
            # If we get here, the format is unexpected
            raise ValueError(
                f"Could not extract embeddings from response. "
                f"Type: {type(result)}, "
                f"Structure: {str(result)[:500]}"
            )
                
        except Exception as e:
            error_msg = str(e)
            
            # Check if this is a "Worker died" or model error
            if "Worker died" in error_msg or "ModelError" in error_msg:
                if retry_count < self.max_retries:
                    logger.warning(
                        f"⚠️  SageMaker worker crashed (attempt {retry_count + 1}/{self.max_retries}). "
                        f"Retrying in {self.retry_delay} seconds..."
                    )
                    time.sleep(self.retry_delay)
                    return self._invoke_endpoint(texts, retry_count + 1)
                else:
                    logger.error(
                        f"❌ SageMaker worker failed after {self.max_retries} retries. "
                        f"Consider reducing batch_size or checking endpoint health."
                    )
                    raise
            else:
                # Different error - don't retry
                logger.error(f"❌ SageMaker invocation failed: {error_msg}")
                raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def embed_query(self, text: str) -> List[float]:
        """
        Generate embedding for a single query (async wrapper)
        
        Args:
            text: Query text
            
        Returns:
            1024-dimensional embedding vector
        """
        try:
            if not text or not text.strip():
                logger.warning("Empty text provided for embedding")
                return [0.0] * self.dimension  # Return zero vector
            
            logger.debug(f"Generating embedding for: {text[:50]}...")
            
            # Call SageMaker endpoint
            embeddings = self._invoke_endpoint([text])
            
            if not embeddings or len(embeddings) == 0:
                logger.error("No embeddings returned from SageMaker")
                return [0.0] * self.dimension
            
            embedding = embeddings[0]
            
            # Validate dimension
            if len(embedding) != self.dimension:
                logger.warning(
                    f"Expected {self.dimension}-dim embedding, got {len(embedding)}-dim"
                )
            
            logger.debug(f"Generated {len(embedding)}-dim embedding")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts
        
        Args:
            texts: List of text strings
            
        Returns:
            List of 1024-dimensional embedding vectors
        """
        try:
            if not texts:
                return []
            
            logger.debug(f"Generating embeddings for {len(texts)} texts...")
            
            all_embeddings = []
            
            # Process in batches to avoid overloading endpoint
            for batch_start in range(0, len(texts), self.batch_size):
                batch_end = min(batch_start + self.batch_size, len(texts))
                batch_texts = texts[batch_start:batch_end]
                
                logger.debug(
                    f"Processing batch {batch_start // self.batch_size + 1} "
                    f"({len(batch_texts)} texts)"
                )
                
                try:
                    batch_embeddings = self._invoke_endpoint(batch_texts)
                    all_embeddings.extend(batch_embeddings)
                except Exception as batch_error:
                    logger.error(f"Batch failed: {batch_error}")
                    # Add zero vectors for failed batch
                    all_embeddings.extend(
                        [[0.0] * self.dimension] * len(batch_texts)
                    )
            
            logger.debug(f"Generated {len(all_embeddings)} embeddings")
            
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            raise
    
    def get_embedding_info(self):
        """Get embedding configuration info"""
        return {
            "provider": "aws_sagemaker",
            "endpoint_name": self.endpoint_name,
            "region": self.region_name,
            "embedding_type": "dense",
            "dimension": self.dimension,
            "batch_size": self.batch_size,
            "model": "BAAI/bge-m3"
        }