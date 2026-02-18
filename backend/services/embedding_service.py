"""
app/services/embedding_service.py
AWS SageMaker BGE-M3 Embedding Service (PRODUCTION VERSION)


"""

import logging
import json
import time
import boto3
from typing import List
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings
from langchain_openai import AzureOpenAIEmbeddings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        try:
            self.embeddings = AzureOpenAIEmbeddings(
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_EMBEDDING_API_VERSION,
                deployment=settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            )

            logger.info(
                "✅ Azure Embedding service initialized | "
                f"Deployment: {settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT}"
            )

        except Exception as e:
            logger.error(
                f"❌ Failed to initialize Embedding service | "
                f"{type(e).__name__}: {str(e)}",
                exc_info=True
            )
            raise
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query (async wrapper)"""
        try:
            if not text or not text.strip():
                logger.warning("Empty text provided for embedding")
                return [0.0] * 1536  # Azure OpenAI embedding dimension
            
            logger.debug(f"Generating embedding for: {text[:50]}...")
            
            # ✅ FIX: Use Azure OpenAI embeddings
            embedding = await self.embeddings.aembed_query(text)
            
            if not embedding or len(embedding) == 0:
                logger.error("No embeddings returned from Azure OpenAI")
                return [0.0] * 1536
            
            logger.debug(f"Generated {len(embedding)}-dim embedding")
            
            return embedding
            
        except Exception as e:
            logger.error(
                f"❌ Failed to generate embedding | "
                f"Text: {text[:50]} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
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