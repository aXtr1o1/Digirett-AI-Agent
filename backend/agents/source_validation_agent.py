"""
agents/source_validation_agent.py

Source Validation Agent
========================
Called inside RAGService._handle_legal() AFTER the first Milvus search.

Responsibilities:
  - Validate that the retrieved Milvus chunks actually correlate with the
    reasoning summary produced by QueryReasoningAgent.
  - If correlated  → return result with explanation and allow pipeline to continue.
  - If not correlated on first attempt → signal a retry.
  - If not correlated after second attempt → signal terminal failure so the
    pipeline can return "Cannot find relevant legal sources."

The agent NEVER generates an answer.  It only validates chunk relevance
and decides whether the pipeline may proceed.

Return shape
------------
{
    "correlated": True | False,
    "explanation": "<why the chunks are / are not relevant>",
    "retry":       True | False,   # only meaningful when correlated=False
}
"""

import logging
import json
import re
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings

logger = logging.getLogger(__name__)


class SourceValidationAgent:
    """
    Validates that Milvus-retrieved chunks are relevant to the reasoning summary.

    Used inside RAGService._handle_legal() to guard against wrong-law retrieval,
    AS/ASA confusion, paragraph misattribution, and off-topic chunks.
    """

    _SYSTEM_PROMPT = """You are a strict legal relevance validator for Norwegian law.

You will receive:
  1. REASONING SUMMARY — the enriched, disambiguated query describing exactly what
     legal information is needed.
  2. RETRIEVED CHUNKS  — text excerpts returned by a vector search.

Your job: decide whether the retrieved chunks actually answer the reasoning summary.

OUTPUT FORMAT — respond with ONLY valid JSON on a single line, no markdown fences:
{"correlated": true, "explanation": "<one sentence why>"}
OR
{"correlated": false, "explanation": "<one sentence why not>"}

VALIDATION RULES:
  1. correlated = true  ONLY when the chunks directly address the legal topic,
     the correct law (AS vs ASA, correct § number), and the correct regulatory body
     stated in the reasoning summary.
  2. correlated = false when:
     - Chunks are from a different law than what the query requires
       (e.g. allmennaksjeloven retrieved instead of aksjeloven, or vice versa)
     - Chunks reference a different paragraph number
     - Chunks are thematically unrelated (procedural when substantive needed)
     - Chunks are index pages, table-of-contents rows, or citation lists
       with no substantive legal text
  3. Be strict. A tangentially related chunk is NOT correlated.
  4. Your explanation must be a single plain sentence — no bullet points."""

    def __init__(self) -> None:
        self._llm = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=0.0,   # Fully deterministic — validation must be consistent
            streaming=False,
        )
        logger.info("✅ SourceValidationAgent initialized")

    # ── Public interface ──────────────────────────────────────────────────

    async def validate(
        self,
        reasoning_summary: str,
        chunks: List[Dict[str, Any]],
        attempt: int = 1,
    ) -> Dict[str, Any]:
        logger.info(
            f"🔍 SourceValidationAgent: validating {len(chunks)} chunks "
            f"(attempt {attempt})"
        )

        if not chunks:
            logger.warning("⚠️  SourceValidationAgent: no chunks to validate")
            return {
                "correlated": False,
                "explanation": "No chunks were retrieved from Milvus.",
                "retry": attempt == 1,
            }

        try:
            chunk_text = self._format_chunks(chunks)

            user_content = (
                f"REASONING SUMMARY:\n{reasoning_summary}\n\n"
                f"RETRIEVED CHUNKS:\n{chunk_text}"
            )

            messages = [
                SystemMessage(content=self._SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ]

            response = await self._llm.agenerate([messages])
            raw = response.generations[0][0].text.strip()

            logger.debug(f"🔍 SourceValidationAgent raw output: {raw}")

            result = self._parse_response(raw)
            correlated = result.get("correlated", False)
            explanation = result.get("explanation", "No explanation provided.")

            logger.info(
                f"🔍 SourceValidationAgent: correlated={correlated} | "
                f"attempt={attempt} | reason='{explanation[:100]}'"
            )

            return {
                "correlated": correlated,
                "explanation": explanation,
                # Signal retry only on the first failure, not the second
                "retry": (not correlated) and (attempt == 1),
            }

        except Exception as exc:
            # On validation error, allow pipeline to continue rather than
            # blocking a potentially valid response.
            logger.warning(
                f"⚠️  SourceValidationAgent failed, allowing pipeline to continue | {exc}"
            )
            return {
                "correlated": True,
                "explanation": f"Validation skipped due to error: {exc}",
                "retry": False,
            }

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _format_chunks(chunks: List[Dict[str, Any]]) -> str:
        """
        Format Milvus chunk dicts into a numbered readable block for the LLM.
        Shows title, law file name, and the first 400 chars of text.
        """
        parts = []
        for i, chunk in enumerate(chunks, start=1):
            title = chunk.get("parent_title", "Unknown")
            file_name = chunk.get("file_name", "unknown-file")
            text = (chunk.get("text") or "")[:400]
            score = round(chunk.get("score", 0.0), 4)
            parts.append(
                f"[Chunk {i} | file={file_name} | title='{title}' | score={score}]\n"
                f"{text}"
            )
        return "\n\n".join(parts)

    @staticmethod
    def _parse_response(raw: str) -> Dict[str, Any]:
        """
        Parse the LLM's JSON response.
        Strips markdown fences if the model wraps the JSON despite instructions.
        """
        # Strip ```json ... ``` fences
        cleaned = re.sub(r"```(?:json)?\s*", "", raw)
        cleaned = re.sub(r"```\s*", "", cleaned).strip()

        # Try to find a JSON object anywhere in the output
        match = re.search(r"\{[^}]+\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # If JSON parsing fails entirely, do a keyword fallback
        lower = raw.lower()
        correlated = "true" in lower and "false" not in lower
        return {
            "correlated": correlated,
            "explanation": "Could not parse validation response from LLM.",
        }