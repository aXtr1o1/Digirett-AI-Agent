import logging
import json
import re
from typing import Any, Dict, List

from openai import AzureOpenAI
from config import settings

logger = logging.getLogger(__name__)


class RerankerAgent:

    def __init__(self) -> None:
        logger.info("🔃 RerankerAgent: using Azure OpenAI deployment for reranking")

        self._client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        )

        self._deployment = settings.AZURE_OPENAI_DEPLOYMENT

        logger.info("✅ RerankerAgent initialized")

    def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:

        if not chunks:
            logger.warning("RerankerAgent: no chunks to rerank")
            return []

        # Limit chunk size to control token usage
        formatted_chunks = "\n\n".join(
            [
                f"{i+1}. {chunk.get('text', '')[:1500]}"
                for i, chunk in enumerate(chunks)
            ]
        )
        logger.info(f"Formatted Chunk: {formatted_chunks}")

        prompt = f"""
You are a legal relevance scoring system.

Query:
{query}

Chunks:
{formatted_chunks}

For EACH chunk assign a relevance score from 0 to 100.

Return ONLY valid JSON in this format:

[
  {{"chunk": 1, "score": 87}},
  {{"chunk": 2, "score": 45}}
]

Higher score = more legally relevant.
Return nothing else.
"""

        try:
            response = self._client.chat.completions.create(
                model=self._deployment,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": "You score legal documents strictly by relevance.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )

            raw_output = response.choices[0].message.content.strip()
            logger.debug(f"Reranker raw output: {raw_output}")

            # Guard: empty response
            if not raw_output:
                logger.warning("Reranker returned empty response — using fallback scores")
                for chunk in chunks:
                    chunk["rerank_score"] = 0.0
                return chunks[:top_k]

            # Strip markdown code fences if present (```json ... ```)
            clean = raw_output
            if clean.startswith("```"):
                clean = re.sub(r"^```[a-zA-Z]*\n?", "", clean)
                clean = re.sub(r"\n?```$", "", clean)
                clean = clean.strip()

            results = json.loads(clean)

            # Attach rerank_score to chunks
            for item in results:
                idx = item["chunk"] - 1
                if 0 <= idx < len(chunks):
                    chunks[idx]["rerank_score"] = float(item["score"])

            # Sort chunks by rerank_score descending
            sorted_chunks = sorted(
                chunks,
                key=lambda x: x.get("rerank_score", 0.0),
                reverse=True,
            )

            return sorted_chunks[:top_k]

        except Exception as e:
            logger.error(f"Reranking failed: {e}", exc_info=True)

            # fallback — return original chunks without scoring
            for chunk in chunks:
                chunk["rerank_score"] = 0.0

            return chunks[:top_k]