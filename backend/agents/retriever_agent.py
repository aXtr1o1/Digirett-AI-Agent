
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RetrieverAgent:
    

    def __init__(self, embedding_service: Any, milvus_client: Any) -> None:
        self._embedding = embedding_service
        self._milvus = milvus_client
        logger.info(" RetrieverAgent initialized")

    async def run(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.45,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        logger.info(
            f" RetrieverAgent: query='{query[:60]}' | top_k={top_k} | min_score={min_score}"
        )

        # Enrich query with last user message for better follow-up retrieval
        contextual_query = self._enrich_query(query, history)

        # Step 1: Generate embedding
        query_embedding = await self._embedding.embed_query(contextual_query)
        logger.debug(f" Embedding dimension: {len(query_embedding)}")

        # Step 2: Search Milvus
        results = self._milvus.search(
            embedding=query_embedding,
            metric_type="IP",
            top_k=top_k,
            min_score=min_score,
        )

        logger.info(f" RetrieverAgent: {len(results)} chunks retrieved")
        for i, chunk in enumerate(results):
            print(f"\n--- CHUNK {i+1} ---")
            print("Score:", chunk["score"])
            print("File:", chunk.get("file_name"))
            print("Parent Title:", chunk.get("parent_title"))
            print("Text Preview:", chunk.get("text")[:500])
            print("article_title", chunk.get("article_title"))
        return results

    # ── Internal ─────────────────────────────────────────────────────────

    @staticmethod
    def _enrich_query(
        query: str,
        history: Optional[List[Dict[str, str]]],
    ) -> str:
        if not history:
            return query

        last_user_msgs = [m["content"] for m in history if m["role"] == "user"]
        if last_user_msgs:
            return last_user_msgs[-1] + " " + query

        return query