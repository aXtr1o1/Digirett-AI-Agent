
import logging
from typing import List

from langchain_openai import AzureOpenAIEmbeddings
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    

    EMBEDDING_DIMENSION = getattr(settings, "AZURE_OPENAI_EMBEDDING_DIMENSION", 1536)

    def __init__(self) -> None:
        try:
            self._embeddings = AzureOpenAIEmbeddings(
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_EMBEDDING_API_VERSION,
                deployment=settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            )
            logger.info(
                f" EmbeddingService initialized | "
                f"deployment={settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT}"
            )
        except Exception as exc:
            logger.error(f" EmbeddingService init failed | {exc}", exc_info=True)
            raise

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=2))
    async def embed_query(self, text: str) -> List[float]:
        
        if not text or not text.strip():
            logger.warning("embed_query received empty text, returning zero vector")
            return [0.0] * self.EMBEDDING_DIMENSION

        try:
            logger.debug(f"Embedding query: '{text[:60]}'")
            vector = await self._embeddings.aembed_query(text)

            if not vector:
                logger.error("Azure OpenAI returned an empty embedding")
                return [0.0] * self.EMBEDDING_DIMENSION

            logger.debug(f" Embedding generated | dim={len(vector)}")
            return vector

        except Exception as exc:
            logger.error(f" embed_query failed | text='{text[:50]}' | {exc}", exc_info=True)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=3), reraise=True)
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        
        if not texts:
            return []

        try:
            logger.debug(f"Embedding batch of {len(texts)} texts")
            vectors = await self._embeddings.aembed_documents(texts)
            logger.debug(f" Batch embedding complete | count={len(vectors)}")
            return vectors
        except Exception as exc:
            logger.error(f"❌ embed_batch failed after retries | {exc}", exc_info=True)
            raise