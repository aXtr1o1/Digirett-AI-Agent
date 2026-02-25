
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from agents.memory_agent import MemoryAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.retriever_agent import RetrieverAgent
from agents.query_reasoning_agent import QueryReasoningAgent
from agents.source_validation_agent import SourceValidationAgent
from db.milvus_client import MilvusClient
from db.redis_client import RedisClient
from db.supabase_client import SupabaseClient
from services.embedding_service import EmbeddingService
from services.llm_service import LLMService

logger = logging.getLogger(__name__)

# Redis key template for storing reasoning context between turns
_REASONING_META_KEY = "reasoning:statute:{conversation_id}"


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
        self._reasoning_agent = QueryReasoningAgent()
        self._validation_agent = SourceValidationAgent()

        logger.info("✅ RAGService initialized with agent routing + reasoning + validation")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PUBLIC INTERFACE  — unchanged
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def process_query(
        self,
        query: str,
        conversation_id: str,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> AsyncIterator[Dict[str, Any]]:

        try:
            logger.info(f"🤖 RAGService: processing query '{query[:60]}'")

            history = self._orchestrator.load_history(
                conversation_id=conversation_id,
                limit=10,
            )
            logger.debug(f"📚 Loaded {len(history)} history messages")

            intent_result = await self._orchestrator.classify(
                query=query,
                conversation_id=conversation_id,
            )
            intent = intent_result["intent"]
            language = intent_result["language"]

            yield {"type": "intent", "data": {"intent": intent, "language": language}}

            if intent == "LEGAL":
                async for event in self._handle_legal(
                    query=query,
                    language=language,
                    top_k=top_k,
                    min_score=min_score,
                    history=history,
                    conversation_id=conversation_id,
                ):
                    yield event
            else:
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
    # LEGAL PIPELINE  — only reasoning context read/write added
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _handle_legal(
        self,
        query: str,
        language: str,
        top_k: int,
        min_score: float,
        history: List[Dict[str, str]],
        conversation_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("⚖️  LEGAL pipeline")

        context_window = history[-4:] if history else []

        
        previous_statute_id = None
        previous_enriched_query = None
        try:
            redis_key = _REASONING_META_KEY.format(conversation_id=conversation_id)
            reasoning_meta = self._redis.get_conversation_meta(redis_key)
            if reasoning_meta:
                previous_statute_id    = reasoning_meta.get("statute_id")
                previous_enriched_query = reasoning_meta.get("enriched_query")
                logger.info(
                    f"📖 Loaded reasoning context | "
                    f"statute_id={previous_statute_id} | "
                    f"prev_query='{str(previous_enriched_query)[:60]}'"
                )
        except Exception as exc:
            logger.warning(f"⚠️  Could not read reasoning meta from Redis | {exc}")
        # ─────────────────────────────────────────────────────────────────

        # Run QueryReasoningAgent with full follow-up context
        reasoning_result = await self._reasoning_agent.run(
            query=query,
            context_window=context_window,
            previous_statute_id=previous_statute_id,
            previous_enriched_query=previous_enriched_query,
        )
        enriched_query     = reasoning_result["enriched_query"]
        primary_statute_id = reasoning_result.get("primary_statute_id")
        response_style     = reasoning_result.get("response_style", "")

        logger.info(f"🧠 Enriched query: '{enriched_query}' | style='{response_style}'")

        # ── WRITE new reasoning context back to Redis ──────────────────────
        # Store for the NEXT turn in this conversation.
        # set_conversation_meta() already exists on RedisClient.
        try:
            redis_key = _REASONING_META_KEY.format(conversation_id=conversation_id)
            self._redis.set_conversation_meta(
                redis_key,
                {
                    "statute_id":     primary_statute_id,
                    "enriched_query": enriched_query,
                },
                ttl=1800,   # same TTL as conversation context
            )
            logger.info(
                f"💾 Saved reasoning context | statute_id={primary_statute_id}"
            )
        except Exception as exc:
            logger.warning(f"⚠️  Could not save reasoning meta to Redis | {exc}")
        # ─────────────────────────────────────────────────────────────────

        search_results, validation_passed = await self._retrieve_and_validate(
            enriched_query=enriched_query,
            reasoning_summary=enriched_query,
            top_k=top_k,
            min_score=min_score,
            history=history,
            language=language,
        )

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
                    "primary_statute_id": primary_statute_id,
                    "chunks_retrieved": 0,
                    "score": 0.1,
                    "confidence": "No correlated sources found after validation",
                    "full_answer": no_result,
                    "rag_chunks": [],
                },
            }
            return

        if not search_results:
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

        rag_context = self._build_context(search_results)

        score_result = await self._llm.generate_legal_answer(
            query=query,
            rag_context=rag_context,
            language=language,
            conversation_history=history,
            response_style=response_style,
        )
        score = score_result["score"]
        confidence = score_result["confidence"]
        scored_answer = score_result["answer"]

        logger.info(f"📊 Score={score} | Confidence={confidence}")

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

        full_answer = ""
        token_count = 0

        async for token in self._llm.generate_legal_stream(
            query=query,
            rag_context=rag_context,
            language=language,
            conversation_history=history,
            response_style=response_style,
        ):
            token_count += 1
            full_answer += token
            yield {"type": "token", "data": token}

        yield {
            "type": "complete",
            "metadata": {
                "intent": "LEGAL",
                "language": language,
                "primary_statute_id": primary_statute_id,
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
    # Dynamic query reformulation — 
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _reformulate_query_with_llm(
        self,
        reasoning_summary: str,
        original_query: str,
        chunks: List[Dict[str, Any]],
    ) -> str:
        try:
            chunk_meta_lines = []
            for i, chunk in enumerate(chunks[:5], start=1):
                title     = chunk.get("parent_title")
                file_name = chunk.get("file_name")
                score     = round(float(chunk.get("score", 0.0)), 3)
                chunk_meta_lines.append(
                    f"  [{i}] title='{title}' | file='{file_name}' | score={score}"
                )
            chunk_meta_block = (
                "\n".join(chunk_meta_lines) if chunk_meta_lines
                else "  (no chunks retrieved — database returned empty results)"
            )

            system_prompt = (
                "You are a legal retrieval query specialist. "
                "Your only job is to rewrite a retrieval query so it targets the correct "
                "legal document, Parent Title in a vector database. "
                "Reason from the mismatch between what was requested and what was retrieved, "
                "then produce one improved retrieval query based on that reason. "
                "Output ONLY the reformulated query — no explanation, no quotes, no labels."
            )

            user_prompt = (
                f"LEGAL REASONING SUMMARY:\n{reasoning_summary}\n\n"
                f"ORIGINAL RETRIEVAL QUERY (attempt 1):\n{original_query}\n\n"
                f"CHUNKS RETRIEVED BY ATTEMPT 1 (likely off-target):\n{chunk_meta_block}\n\n"
                "The retrieved chunks did not satisfy validation. "
                "Study the chunk metadata above to understand what the database returned. "
                "Write a improved retrieval query that steers away from those documents "
                "and toward the correct legal source implied by the reasoning summary. "
                "Include specific law names, article numbers, parent_title or legal concepts "
                "from that query and also mention not include law name from chunks.\n\n"
                "Reformulated retrieval query:"
            )

            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
            response = await self._llm._llm.agenerate([messages])
            reformulated = response.generations[0][0].text.strip()

            if not reformulated or len(reformulated) > 500:
                logger.warning(
                    "⚠️  _reformulate_query_with_llm: output invalid, using original query"
                )
                return original_query

            logger.info(f"🔄 Reformulated query (attempt 2): '{reformulated}'")
            return reformulated

        except Exception as exc:
            logger.warning(
                f"⚠️  _reformulate_query_with_llm failed ({exc}), using original query"
            )
            return original_query

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Retrieve + Validate — 
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _retrieve_and_validate(
        self,
        enriched_query: str,
        reasoning_summary: str,
        top_k: int,
        min_score: float,
        history: List[Dict[str, str]],
        language: str,
        statute_filter: Optional[str] = None,
    ):
        retrieval_query = enriched_query

        for attempt in (1, 2):
            logger.info(
                f"🔎 RetrieverAgent attempt {attempt} | query='{retrieval_query}'"
            )

            search_results = await self._retriever_agent.run(
                query=retrieval_query,
                top_k=top_k,
                min_score=min_score,
                history=history,
                statute_filter=statute_filter,
            )

            logger.info(f"📦 Retrieved {len(search_results)} chunks (attempt {attempt})")

            if not search_results:
                if attempt == 1:
                    logger.warning(
                        "⚠️  Zero results on attempt 1, reformulating from reasoning summary..."
                    )
                    retrieval_query = await self._reformulate_query_with_llm(
                        reasoning_summary=reasoning_summary,
                        original_query=enriched_query,
                        chunks=[],
                    )
                    continue
                else:
                    logger.warning("⚠️  Zero results on attempt 2 — terminal failure")
                    return [], False

            validation = await self._validation_agent.validate(
                reasoning_summary=reasoning_summary,
                chunks=search_results,
                attempt=attempt,
            )

            if validation["correlated"]:
                logger.info(
                    f"✅ Validation passed (attempt {attempt}) | "
                    f"{validation.get('explanation', '')}"
                )
                return search_results, True

            logger.warning(
                f"⚠️  Validation failed (attempt {attempt}) | "
                f"{validation.get('explanation', '')}"
            )

            if attempt == 1 and validation.get("retry", True):
                logger.info(
                    "🔄 Reformulating retrieval query from failed chunk metadata..."
                )
                retrieval_query = await self._reformulate_query_with_llm(
                    reasoning_summary=reasoning_summary,
                    original_query=enriched_query,
                    chunks=search_results,
                )
                continue

            return [], False

        return [], False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS  — unchanged
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_context(self, search_results: List[Dict[str, Any]]) -> str:
        parts = []
        for i, result in enumerate(search_results, start=1):
            title = result.get("parent_title", "Unknown")
            text = result.get("text", "")
            parts.append(f"[Kilde {i}: {title}]\n{text}\n")
        return "\n---\n".join(parts)

    def _format_sources(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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