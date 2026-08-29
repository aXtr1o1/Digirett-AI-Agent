import copy
import logging
import time
from typing import Any, Dict, List, Optional

from openai import AzureOpenAI
from pydantic import BaseModel, Field

from config import settings
from utils.json_response_parser import parse_json_response

from prompts.reranker_prompts import RERANKER_PROMPT_TEMPLATE

def _safe_int(val: Any, default: int) -> int:
    return val if isinstance(val, int) else default

# ── OPERATIONAL CONSTANTS & RATIONALE ────────────────────────────────
# Configurable constants loaded from settings with sane upper caps
MAX_RERANK_CHARS = min(_safe_int(getattr(settings, "RERANKER_MAX_CHARS", 1500), 1500), 4000)
DEFAULT_TOP_K = min(_safe_int(getattr(settings, "RERANKER_DEFAULT_TOP_K", getattr(settings, "DEFAULT_TOP_K", 5)), 5), 20)
MAX_RETRIES = min(_safe_int(getattr(settings, "RERANKER_MAX_RETRIES", 2), 2), 5)
RETRY_DELAY = getattr(settings, "RERANKER_RETRY_DELAY", 0.5) if isinstance(getattr(settings, "RERANKER_RETRY_DELAY", 0.5), (int, float)) else 0.5


logger = logging.getLogger(__name__)


class ChunkScoreItem(BaseModel):
    chunk: int = Field(
        ...,
        ge=1,
        description="1-indexed chunk position identifier matching LLM prompt input"
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Legal relevance score from 0.0 (irrelevant) to 100.0 (highly relevant)"
    )



class RerankerAgent:

    def __init__(self, client: Optional[Any] = None) -> None:
        if client is not None:
            self._client = client
        else:
            self._client = AzureOpenAI(
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            )
        self._deployment = settings.AZURE_OPENAI_DEPLOYMENT
        logger.info("[OK] RerankerAgent initialized")

    def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: int = DEFAULT_TOP_K,
    ) -> List[Dict[str, Any]]:

        if not chunks:
            logger.warning("RerankerAgent: no chunks to rerank")
            return []

        # Non-mutating copy of input chunks with default 0.0 score
        copied_chunks = [copy.deepcopy(c) for c in chunks]
        for c in copied_chunks:
            c["rerank_score"] = 0.0


        # Sensitive log suppression: log metrics only, never full text
        logger.info("Reranking chunks", extra={"chunk_count": len(chunks), "top_k": top_k})

        # Format chunks using MAX_RERANK_CHARS constant
        formatted_chunks = "\n\n".join(
            [
                f"{i+1}. {chunk.get('text', '')[:MAX_RERANK_CHARS]}"
                for i, chunk in enumerate(copied_chunks)
            ]
        )

        prompt = RERANKER_PROMPT_TEMPLATE.format(query=query,formatted_chunks=formatted_chunks,)

        # Execution with exponential backoff retry policy
        response = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._deployment,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": "You score legal documents strictly by relevance."},
                        {"role": "user", "content": prompt},
                    ],
                )
                break
            except Exception as exc:
                if attempt < MAX_RETRIES:
                    logger.warning(f" RerankerAgent: attempt {attempt + 1} failed: {exc}. Retrying...")
                    time.sleep(RETRY_DELAY * (2 ** attempt))
                else:
                    logger.error(f" RerankerAgent failed after retries: {exc}")

        if response and response.choices and response.choices[0].message.content:
            raw_output = response.choices[0].message.content.strip()
            parsed_data = parse_json_response(raw_output)

            # Accept list of dicts directly from parse_json_response if list, or parse list
            if not isinstance(parsed_data, list):
                # parse_json_response returns dict or None; if wrapped in list, inspect raw JSON
                import json
                try:
                    parsed_data = json.loads(raw_output)
                except Exception:
                    parsed_data = None

            if isinstance(parsed_data, list):
                for item in parsed_data:
                    if isinstance(item, dict) and "chunk" in item and "score" in item:
                        try:
                            validated_item = ChunkScoreItem(
                                chunk=int(item["chunk"]),
                                score=float(item["score"]),
                            )
                            idx = validated_item.chunk - 1
                            if 0 <= idx < len(copied_chunks):
                                copied_chunks[idx]["rerank_score"] = round(validated_item.score, 2)

                        except Exception as val_exc:
                            logger.warning(f" RerankerAgent: invalid score item '{item}': {val_exc}")

                sorted_chunks = sorted(
                    copied_chunks,
                    key=lambda x: x.get("rerank_score", 0.0),
                    reverse=True,
                )
                return sorted_chunks[:top_k]

        # Fallback — return original copied chunks with 0.0 score
        for chunk in copied_chunks:
            chunk["rerank_score"] = 0.0
        return copied_chunks[:top_k]