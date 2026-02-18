import logging
from typing import List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from backend.config import settings

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Azure OpenAI embedding generator."""

    def __init__(self):
        self.dimension = settings.EMBEDDING_DIMENSION
        self._client: Optional[httpx.AsyncClient] = httpx.AsyncClient(timeout=30.0)
        logger.info(
            f"EmbeddingGenerator init azure_deployment={settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT} dim={self.dimension}"
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException, ValueError)),
        reraise=True,
    )
    async def embed_query(self, text: str) -> List[float]:
        q = (text or "").strip()
        if not q:
            # do NOT retrieve on empty; caller should handle, but keep safe
            return [0.0] * self.dimension

        url = (
            f"{settings.AZURE_OPENAI_EMBED_ENDPOINT}/openai/deployments/"
            f"{settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT}/embeddings"
            f"?api-version={settings.AZURE_OPENAI_EMBED_API_VERSION}"
        )
        headers = {"api-key": settings.AZURE_OPENAI_EMBED_API_KEY, "Content-Type": "application/json"}
        payload = {"input": q}

        r = await self._client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

        emb = data["data"][0]["embedding"]
        if len(emb) != self.dimension:
            raise ValueError(f"Embedding dim mismatch: expected {self.dimension}, got {len(emb)}")

        return [float(x) for x in emb]

    async def aclose(self):
        if self._client:
            await self._client.aclose()
