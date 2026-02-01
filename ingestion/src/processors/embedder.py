"""
SageMaker BGE Embedder - TOKEN-AWARE VERSION
Works with token-based chunking (no truncation needed)

Key features:
1. Processes token-bounded chunks safely
2. Batch processing with configurable size
3. Automatic retry on worker crashes
4. No text truncation (chunks are already optimally sized)
5. Progress tracking and detailed logging
"""

import logging
import json
import time
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class TokenAwareSageMakerEmbedder:
    """
    Embedder for token-bounded chunks.
    Processes chunks in safe batches without truncation.
    """
    
    def __init__(
        self,
        endpoint_name: str,
        region_name: str = "ap-south-1",
        max_retries: int = 3,
        retry_delay: int = 15,
        chunk_delay: float = 1.0,  # Faster processing since chunks are pre-sized
        batch_size: int = 1,  # Process 5 chunks at a time
        warn_token_threshold: int = 400  # Warn if chunks exceed this
    ):
        """
        Initialize token-aware embedder.
        
        Args:
            endpoint_name: SageMaker endpoint name
            region_name: AWS region
            max_retries: Maximum retry attempts on failure
            retry_delay: Seconds to wait before retry
            chunk_delay: Seconds between batches (can be shorter with pre-sized chunks)
            batch_size: Number of chunks to process in parallel
            warn_token_threshold: Log warning if chunk exceeds this token count
        """
        import boto3
        
        self.endpoint_name = endpoint_name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.chunk_delay = chunk_delay
        self.batch_size = batch_size
        self.warn_token_threshold = warn_token_threshold
        
        self.client = boto3.client(
            "sagemaker-runtime",
            region_name=region_name
        )
        
        logger.info(
            f"✅ Token-Aware SageMaker Embedder initialized | "
            f"batch_size={batch_size} | chunk_delay={chunk_delay}s | "
            f"No truncation (using pre-sized chunks)"
        )

    def _invoke_batch(
        self,
        texts: List[str],
        retry_count: int = 0
    ) -> List[List[float]]:
        """
        Invoke endpoint for a BATCH of texts with retry logic.
        
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
            
            # Build payload
            payload = {"inputs": texts}
            
            # Invoke endpoint
            response = self.client.invoke_endpoint(
                EndpointName=self.endpoint_name,
                ContentType="application/json",
                Body=json.dumps(payload)
            )
            
            # Parse response
            result = json.loads(response["Body"].read().decode())
            
            # Extract embeddings
            if isinstance(result, list):
                # Result is directly a list of embeddings
                return result
            elif isinstance(result, dict) and "embeddings" in result:
                return result["embeddings"]
            else:
                logger.error(f"Unexpected response format: {type(result)}")
                return [None] * len(texts)
                
        except Exception as e:
            error_msg = str(e)
            
            # Check for worker crash or memory error
            if any(err in error_msg for err in ["Worker died", "ModelError", "Memory", "OOM"]):
                if retry_count < self.max_retries:
                    # Exponential backoff
                    wait_time = self.retry_delay * (2 ** retry_count)
                    logger.warning(
                        f"⚠️  Worker crashed on batch of {len(texts)} "
                        f"(attempt {retry_count + 1}/{self.max_retries}). "
                        f"Waiting {wait_time}s..."
                    )
                    time.sleep(wait_time)
                    return self._invoke_batch(texts, retry_count + 1)
                else:
                    logger.error(
                        f"❌ Worker failed after {self.max_retries} retries "
                        f"for batch of {len(texts)}"
                    )
                    return [None] * len(texts)
            else:
                logger.error(f"❌ Invocation failed: {error_msg}")
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
        3. Delay between batches for VRAM stability
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
                    oversized_count += 1
                    logger.warning(
                        f"⚠️  Chunk {i} has {token_count} tokens "
                        f"(threshold: {self.warn_token_threshold})"
                    )
                
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


class SageMakerBGEEmbedder(TokenAwareSageMakerEmbedder):
    """Alias for compatibility"""
    pass


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Example chunks with token counts
    example_chunks = [
        {
            "text": "This is a test chunk with some Norwegian legal text.",
            "token_count": 12,
            "chunk_id": "test-001"
        },
        {
            "text": "Another chunk with more content to test the embedder.",
            "token_count": 11,
            "chunk_id": "test-002"
        }
    ]
    
    # Initialize embedder
    embedder = SageMakerBGEEmbedder(
        endpoint_name="embedding-bge-m3-endpoint",
        region_name="ap-south-1",
        batch_size=1,
        chunk_delay=0.5
    )
    
    # Generate embeddings
    print("\n🧠 Testing token-aware embedder...")
    result_chunks = embedder.embed_chunks(example_chunks)
    
    # Show results
    for chunk in result_chunks:
        has_embedding = chunk.get('embedding') is not None
        print(f"  Chunk {chunk['chunk_id']}: {'✅ Success' if has_embedding else '❌ Failed'}")