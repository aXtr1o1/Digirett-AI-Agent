"""
services/rag_service.py

No existing logic was modified.
Two new agents were inserted into the LEGAL pipeline only:

  • QueryReasoningAgent — runs AFTER MemoryAgent, BEFORE IntentAgent
    (technically: classified as LEGAL first, then reasoning runs before embedding)
    Position: between history load and RetrieverAgent.run()

  • SourceValidationAgent — runs AFTER RetrieverAgent.run(), with one retry allowed.

CASUAL pipeline is completely unchanged.
All saving logic, Redis logic, scoring threshold, and embedding model are unchanged.
"""

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from agents.memory_agent import MemoryAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.retriever_agent import RetrieverAgent
# ── NEW AGENTS ────────────────────────────────────────────────────────────────
from agents.query_reasoning_agent import QueryReasoningAgent
from agents.source_validation_agent import SourceValidationAgent
# ─────────────────────────────────────────────────────────────────────────────
from db.milvus_client import MilvusClient
from db.redis_client import RedisClient
from db.supabase_client import SupabaseClient
from services.embedding_service import EmbeddingService
from services.llm_service import LLMService

logger = logging.getLogger(__name__)


class RAGService:

    def __init__(
        self,
        llm_service: LLMService,
        milvus_client: MilvusClient,
        redis_client: RedisClient,
        supabase_client: SupabaseClient,
        embedding_service: EmbeddingService,
    ) -> None:
        self._llm = llm_service
        self._milvus = milvus_client
        self._redis = redis_client
        self._supabase = supabase_client
        self._embedding = embedding_service

        # ── Existing agents (unchanged) ────────────────────────────────────
        self._memory_agent = MemoryAgent(
            redis_client=redis_client,
            supabase_client=supabase_client,
        )
        self._retriever_agent = RetrieverAgent(
            embedding_service=embedding_service,
            milvus_client=milvus_client,
        )
        self._orchestrator = OrchestratorAgent(
            intent_agent=llm_service.get_intent_agent(),
            memory_agent=self._memory_agent,
            generator_agent=llm_service.get_generator_agent(),
        )

        # ── NEW: instantiate the two new agents ────────────────────────────
        self._reasoning_agent = QueryReasoningAgent()
        self._validation_agent = SourceValidationAgent()

        logger.info("✅ RAGService initialized with agent routing + reasoning + validation")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PUBLIC INTERFACE  (unchanged signature)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def process_query(
        self,
        query: str,
        conversation_id: str,
        top_k: int = 5,
        min_score: float = 0.45,
    ) -> AsyncIterator[Dict[str, Any]]:

        try:
            logger.info(f"🤖 RAGService: processing query '{query[:60]}'")

            # Step 1 — Load conversation history  (UNCHANGED)
            history = self._orchestrator.load_history(
                conversation_id=conversation_id,
                limit=10,
            )
            logger.debug(f"📚 Loaded {len(history)} history messages")

            # Step 2 — Classify intent  (UNCHANGED)
            intent_result = await self._orchestrator.classify(
                query=query,
                conversation_id=conversation_id,
            )
            intent = intent_result["intent"]
            language = intent_result["language"]

            yield {"type": "intent", "data": {"intent": intent, "language": language}}

            # Step 3 — Route to the correct pipeline  (UNCHANGED)
            if intent == "LEGAL":
                async for event in self._handle_legal(
                    query=query,
                    language=language,
                    top_k=top_k,
                    min_score=min_score,
                    history=history,
                ):
                    yield event
            else:
                # CASUAL path is completely unchanged
                async for event in self._handle_casual(query, history, language):
                    yield event

        except Exception as exc:
            logger.error(
                f"❌ RAGService.process_query failed | query='{query[:50]}' | {exc}",
                exc_info=True,
            )
            yield {"type": "error", "message": str(exc)}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CASUAL PIPELINE  — completely unchanged
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _handle_casual(
        self,
        query: str,
        history: List[Dict[str, str]],
        language: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("💬 CASUAL pipeline")

        yield {"type": "sources", "data": []}

        full_answer = ""
        token_count = 0

        async for token in self._llm.generate_casual_stream(
            query=query,
            conversation_history=history,
        ):
            token_count += 1
            full_answer += token
            yield {"type": "token", "data": token}

        yield {
            "type": "complete",
            "metadata": {
                "intent": "CASUAL",
                "language": language,
                "tokens_generated": token_count,
                "score": 1.0,
                "confidence": "Casual conversation",
                "full_answer": full_answer,
                "rag_chunks": [],
            },
        }
        logger.info(f"✅ CASUAL pipeline complete | tokens={token_count}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LEGAL PIPELINE  — two new steps inserted, everything else unchanged
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _handle_legal(
        self,
        query: str,
        language: str,
        top_k: int,
        min_score: float,
        history: List[Dict[str, str]],
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("⚖️  LEGAL pipeline")

        # ── NEW STEP A: Query Reasoning Summary ───────────────────────────
        # Inserted between MemoryAgent (already ran in process_query) and
        # RetrieverAgent (embedding step).
        # context_window = last 4 messages (short window for reasoning context)
        context_window = history[-4:] if history else []
        enriched_query = await self._reasoning_agent.run(
            query=query,
            context_window=context_window,
        )
        logger.info(f"🧠 Enriched query: '{enriched_query}'")
        # ─────────────────────────────────────────────────────────────────

        # ── NEW STEP B: Retrieve → Validate → (optional retry) ───────────
        search_results, validation_passed = await self._retrieve_and_validate(
            enriched_query=enriched_query,
            reasoning_summary=enriched_query,
            top_k=top_k,
            min_score=min_score,
            history=history,
            language=language,
        )

        # If both attempts failed validation, return terminal "not found" response
        if not validation_passed:
            logger.warning("⚠️  Source validation failed after 2 attempts — returning not-found")
            yield {"type": "sources", "data": []}

            no_result = (
                "Jeg finner ingen relevante juridiske kilder som samsvarer med spørsmålet ditt "
                "i den tilgjengelige Lovdata-databasen. Vennligst prøv å omformulere spørsmålet "
                "eller oppgi mer spesifikke detaljer om hvilken lov eller paragraf du søker etter."
                if language == "norwegian"
                else
                "Cannot find relevant legal sources from my knowledge. "
                "The retrieved documents did not match the legal topic of your question. "
                "Please try rephrasing your query or providing more specific details about "
                "the law or paragraph you are looking for."
            )

            for char in no_result:
                yield {"type": "token", "data": char}

            yield {
                "type": "complete",
                "metadata": {
                    "intent": "LEGAL",
                    "language": language,
                    "chunks_retrieved": 0,
                    "score": 0.1,
                    "confidence": "No correlated sources found after validation",
                    "full_answer": no_result,
                    "rag_chunks": [],
                },
            }
            return
        # ─────────────────────────────────────────────────────────────────

        # From here on — everything is UNCHANGED from the original _handle_legal

        if not search_results:
            # This path handles the case where Milvus returned zero results
            # even after retry (validation_passed is True but results empty
            # because validation agent allowed fallback).
            logger.warning("⚠️  No Milvus results found")
            yield {"type": "sources", "data": []}

            no_result = (
                "Jeg finner ingen relevante lovutdrag i den tilgjengelige Lovdata-databasen "
                "som direkte svarer på dette spørsmålet. "
                "Det kan være at spørsmålet er formulert for generelt eller gjelder et område "
                "som ikke dekkes av tilgjengelige kilder. "
                "Du kan prøve å omformulere spørsmålet eller gi mer spesifikke detaljer for et mer presist svar."
                if language == "norwegian"
                else
                "I cannot find any relevant legal excerpts from my knowledge. "
                "The question may be too general or relate to an area not covered in the available sources. "
                "You may try rephrasing the question or providing more specific details for a more accurate response."
            )

            for char in no_result:
                yield {"type": "token", "data": char}

            yield {
                "type": "complete",
                "metadata": {
                    "intent": "LEGAL",
                    "language": language,
                    "chunks_retrieved": 0,
                    "score": 0.1,
                    "confidence": "No sources found",
                    "full_answer": no_result,
                    "rag_chunks": [],
                },
            }
            return

        # Step 2 — Build context string for the LLM  (UNCHANGED)
        rag_context = self._build_context(search_results)

        # Step 3 — Score  (UNCHANGED)
        score_result = await self._llm.generate_legal_answer(
            query=query,
            rag_context=rag_context,
            language=language,
            conversation_history=history,
        )
        score = score_result["score"]
        confidence = score_result["confidence"]
        scored_answer = score_result["answer"]

        logger.info(f"📊 Score={score} | Confidence={confidence}")

        # Step 4 — Emit sources  (UNCHANGED)
        visible_sources = []
        visible_chunks = []

        if score >= 0.5:
            visible_chunks = search_results
            visible_sources = list({r.get("url") for r in search_results if r.get("url")})
            yield {"type": "sources", "data": visible_sources}
            logger.info(f"✅ Emitting {len(visible_sources)} source URLs (score >= 0.5)")
        else:
            yield {"type": "sources", "data": []}
            logger.info("⚠️  Hiding sources (score < 0.5)")

        # Step 5 — Stream clean answer  (UNCHANGED)
        full_answer = ""
        token_count = 0

        async for token in self._llm.generate_legal_stream(
            query=query,
            rag_context=rag_context,
            language=language,
            conversation_history=history,
        ):
            token_count += 1
            full_answer += token
            yield {"type": "token", "data": token}

        yield {
            "type": "complete",
            "metadata": {
                "intent": "LEGAL",
                "language": language,
                "chunks_retrieved": len(search_results),
                "tokens_generated": token_count,
                "score": score,
                "confidence": confidence,
                "full_answer": scored_answer,
                "rag_chunks": visible_chunks,
            },
        }
        logger.info(
            f"✅ LEGAL pipeline complete | chunks={len(search_results)} | tokens={token_count}"
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # NEW: Retrieve + Validate with one retry
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _retrieve_and_validate(
        self,
        enriched_query: str,
        reasoning_summary: str,
        top_k: int,
        min_score: float,
        history: List[Dict[str, str]],
        language: str,
    ):
        """
        Run Milvus retrieval → validation.
        If validation fails on attempt 1, retry retrieval and validate again.
        If validation fails on attempt 2, return ([], False).

        Returns:
            (search_results: List[Dict], validation_passed: bool)
        """
        for attempt in (1, 2):
            logger.info(f"🔎 RetrieverAgent attempt {attempt} | query='{enriched_query[:60]}'")

            # Use enriched_query (from QueryReasoningAgent) instead of raw query
            search_results = await self._retriever_agent.run(
                query=enriched_query,
                top_k=top_k,
                min_score=min_score,
                history=history,
            )

            logger.info(f"📦 Retrieved {len(search_results)} chunks (attempt {attempt})")

            if not search_results:
                # No results at all — skip validation, signal retry on attempt 1
                if attempt == 1:
                    logger.warning("⚠️  No results on attempt 1, retrying...")
                    continue
                else:
                    logger.warning("⚠️  No results on attempt 2 either")
                    return [], False

            # Validate the retrieved chunks
            validation = await self._validation_agent.validate(
                reasoning_summary=reasoning_summary,
                chunks=search_results,
                attempt=attempt,
            )

            if validation["correlated"]:
                logger.info(
                    f"✅ SourceValidationAgent: chunks correlated (attempt {attempt}) | "
                    f"{validation['explanation']}"
                )
                return search_results, True

            # Not correlated
            logger.warning(
                f"⚠️  SourceValidationAgent: not correlated (attempt {attempt}) | "
                f"{validation['explanation']}"
            )

            if attempt == 1 and validation.get("retry"):
                logger.info("🔄 Retrying retrieval...")
                continue

            # Attempt 2 failed — terminal failure
            return [], False

        # Should never reach here, but safety fallback
        return [], False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS  — completely unchanged
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_context(self, search_results: List[Dict[str, Any]]) -> str:
        """Format Milvus results into a source-numbered context string for the LLM."""
        parts = []
        for i, result in enumerate(search_results, start=1):
            title = result.get("parent_title", "Unknown")
            text = result.get("text", "")
            parts.append(f"[Kilde {i}: {title}]\n{text}\n")
        return "\n---\n".join(parts)

    def _format_sources(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format Milvus results into the source list shape expected by the frontend."""
        sources = []
        for result in search_results:
            url = result.get("url") or result.get("file_url")
            sources.append({
                "title": result.get("parent_title", "Unknown"),
                "url": url,
                "chunk_text": result.get("text", "")[:200] + "...",
                "relevance_score": round(result.get("score", 0.0), 4),
                "metadata": {
                    "file_name": result.get("file_name", ""),
                    "chunk_index": result.get("chunk_index", 0),
                    "parent_type": result.get("parent_type", ""),
                },
            })
        return sources