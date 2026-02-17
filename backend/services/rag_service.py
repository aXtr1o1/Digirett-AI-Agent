

import logging
from typing import Dict, Any, AsyncIterator, Optional, List

from ..services.llm_service import (
    LLMService,
    IntentAgent,
    MemoryAgent,
    GeneratorAgent,
    OrchestratorAgent,
)
from ..db.milvus_client import MilvusClient
from ..db.redis import RedisClient
from ..db.supabase import SupabaseClient
from ..services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RETRIEVER AGENT (defined here — needs milvus + embedding clients)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RetrieverAgent:

    def __init__(
        self,
        embedding_service: EmbeddingService,
        milvus_client: MilvusClient,
    ):
        self.embedding = embedding_service
        self.milvus = milvus_client
        logger.info("✅ RetrieverAgent initialized")

    async def run(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.5,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        
        logger.info(f"🔎 RetrieverAgent.run: query='{query[:60]}...' top_k={top_k}")

        contextual_query = query
        if history:
            last_user_messages = [
                msg["content"]
                for msg in history
                if msg["role"] == "user"
            ]
            if last_user_messages:
                contextual_query = last_user_messages[-1] + " " + query

        # ── Generate embedding ─────────────────────────────────
        query_embedding = await self.embedding.embed_query(contextual_query)
        logger.debug(f"🔢 RetrieverAgent: {len(query_embedding)}-dim embedding")

        # ── Search Milvus ──────────────────────────────────────
        search_results = self.milvus.search(
            embedding=query_embedding,
            top_k=top_k,
            min_score=min_score,
        )

        logger.info(f"✅ RetrieverAgent: {len(search_results)} results returned")
        return search_results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RAG SERVICE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RAGService:
   

    def __init__(
        self,
        llm_service: LLMService,
        milvus_client: MilvusClient,
        redis_client: RedisClient,
        supabase_client: SupabaseClient,
        embedding_service: EmbeddingService,
    ):
        self.llm      = llm_service
        self.milvus   = milvus_client
        self.redis    = redis_client
        self.supabase = supabase_client
        self.embedding = embedding_service

        # ── Wire up agents ─────────────────────────────────────
        self._memory_agent    = MemoryAgent(
            redis_client=redis_client,
            supabase_client=supabase_client,
        )
        self._retriever_agent = RetrieverAgent(
            embedding_service=embedding_service,
            milvus_client=milvus_client,
        )
        self._orchestrator    = OrchestratorAgent(
            intent_agent=llm_service.get_intent_agent(),
            memory_agent=self._memory_agent,
            generator_agent=llm_service.get_generator_agent(),
        )

        logger.info("✅ RAG service initialized with agent routing")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # process_query  ── UNCHANGED public signature
    # Internal routing now goes through OrchestratorAgent
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def process_query(
        self,
        query: str,
        conversation_id: str,
        min_score: float = 0.0,
        top_k: int = 3,
    ) -> AsyncIterator[Dict[str, Any]]:
        
        try:
            logger.info(f"🤖 Processing query with agent routing: '{query[:50]}...'")

            # ── STEP 1: OrchestratorAgent loads history (MemoryAgent) ──
            llm_history = self._orchestrator.load_history(
                conversation_id=conversation_id,
                limit=10,
            )
            logger.debug(f"📚 Loaded conversation history: {len(llm_history)} messages")

            # ── STEP 2: OrchestratorAgent classifies intent (IntentAgent) ──
            intent_result = await self._orchestrator.classify(
                query=query,
                conversation_id=conversation_id,
            )
            intent   = intent_result["intent"]
            language = intent_result["language"]

            logger.info(f"🎯 Intent: {intent}, Language: {language}")

            # Yield intent event (unchanged)
            yield {
                "type": "intent",
                "data": {
                    "intent": intent,
                    "language": language,
                },
            }

            # ── STEP 3: Route to appropriate handler (unchanged handlers) ──
            if intent == "CASUAL":
                async for event in self._handle_casual(query, llm_history, language):
                    yield event

            elif intent == "LEGAL":
                async for event in self._handle_legal(
                    query=query,
                    language=language,
                    top_k=top_k,
                    min_score=min_score,
                    history=llm_history,
                ):
                    yield event

            else:
                logger.warning(f"⚠️  Unknown intent: {intent}, defaulting to CASUAL")
                async for event in self._handle_casual(query, llm_history, language):
                    yield event

        except Exception as e:
            logger.error(
                f"❌ Query processing failed | "
                f"Query: {query[:50]} | "
                f"Conversation: {conversation_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            yield {
                "type": "error",
                "message": f"Failed to process query: {str(e)}",
            }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # _handle_casual  ── 100% UNCHANGED
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _handle_casual(
        self,
        query: str,
        history: List[Dict[str, str]],
        language: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        
        try:
            logger.info("💬 Handling CASUAL query (no RAG)")

            yield {"type": "sources", "data": []}

            full_answer = ""
            token_count = 0

            async for token in self.llm.generate_casual_stream(
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
                },
            }

            logger.info(f"✅ CASUAL response complete | Tokens: {token_count}")

        except Exception as e:
            logger.error(
                f"❌ CASUAL handler failed | "
                f"Query: {query[:50]} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            raise


    async def _handle_legal(
        self,
        query: str,
        language: str,
        history: List[Dict[str, str]],
        top_k: int,
        min_score: float,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Handle LEGAL queries (with RAG and scoring).

        Flow (identical to original, retrieval now via RetrieverAgent):
        1. RetrieverAgent: embed + search Milvus
        2. Build RAG context
        3. generate_legal_answer: get score (streaming internally, [SCORE:x.x] parsed)
        4. Yield sources only if score >= 0.5
        5. generate_legal_stream: stream clean answer to frontend
        """
        try:
            logger.info("⚖️  Handling LEGAL query (with RAG)")

            # ── STEP 1: RetrieverAgent does embedding + Milvus search ──
            search_results = await self._retriever_agent.run(
                query=query,
                top_k=top_k,
                min_score=min_score,
                history=history,
            )

            if not search_results:
                logger.warning("⚠️  No results from Milvus")

                yield {"type": "sources", "data": []}

                no_result_msg = (
                    "Jeg finner ingen relevante lovutdrag i den tilgjengelige "
                    "Lovdata-databasen som direkte svarer på dette spørsmålet."
                    if language == "norwegian"
                    else "I cannot find any relevant legal excerpts in the available "
                    "Lovdata database that directly answer this question."
                )

                for char in no_result_msg:
                    yield {"type": "token", "data": char}

                yield {
                    "type": "complete",
                    "metadata": {
                        "intent": "LEGAL",
                        "language": language,
                        "chunks_retrieved": 0,
                        "score": 0.1,
                        "confidence": "No sources found",
                        "full_answer": no_result_msg,
                    },
                }
                return

            # ── STEP 2: Build RAG context (unchanged) ──────────
            rag_context = self._build_context(search_results)
            logger.debug(f"📄 Built RAG context: {len(rag_context)} chars")

            
            logger.info("🎯 Generating legal answer with score...")
            result = await self.llm.generate_legal_answer(
                query=query,
                rag_context=rag_context,
                language=language,
                conversation_history=history,
            )

            answer     = result["answer"]
            score      = result["score"]
            confidence = result["confidence"]
            tokens_used = result["tokens_used"]

            logger.info(f"📊 Score: {score}, Confidence: {confidence}")

            # ── STEP 4: Yield sources (only if score >= 0.5) ────
            # UNCHANGED logic — same rule as original
            if score >= 0.5:
                urls = list({
                    r.get("url")
                    for r in search_results
                    if r.get("url")
                })
                yield {"type": "sources", "data": urls}
                logger.info(f"✅ Showing {len(urls)} source URLs (score >= 0.5)")
            else:
                yield {"type": "sources", "data": []}
                logger.info("⚠️  Hiding sources (score < 0.5)")

            # ── STEP 5: Stream answer to frontend ──────────────
            # generate_legal_stream strips [SCORE:x.x] — clean tokens only
            full_answer = ""
            token_count = 0

            async for token in self.llm.generate_legal_stream(
                query=query,
                rag_context=rag_context,
                language=language,
                conversation_history=history,
            ):
                token_count += 1
                full_answer += token
                yield {"type": "token", "data": token}

            # ── STEP 6: Yield completion (unchanged shape) ──────
            yield {
                "type": "complete",
                "metadata": {
                    "intent": "LEGAL",
                    "language": language,
                    "chunks_retrieved": len(search_results),
                    "tokens_generated": tokens_used,
                    "score": score,
                    "confidence": confidence,
                    "full_answer": answer,      # from generate_legal_answer (score-parsed)
                    "rag_chunks": search_results,
                },
            }

            logger.info(
                "LEGAL_QUERY_COMPLETE",
                extra={
                    "event": "legal_query_complete",
                    "query": query[:200],
                    "language": language,
                    "chunks_retrieved": len(search_results),
                    "tokens_generated": tokens_used,
                    "score": score,
                    "confidence": confidence,
                },
            )

        except Exception as e:
            logger.error(
                f"❌ LEGAL handler failed | "
                f"Query: {query[:50]} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            raise

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # _build_context  ── 100% UNCHANGED
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_context(self, search_results: List[Dict[str, Any]]) -> str:
        """Build context string from Milvus results"""
        context_parts = []
        for i, result in enumerate(search_results, 1):
            parent_title = result.get("parent_title", "Unknown")
            text = result.get("text", "")
            context_parts.append(f"[Kilde {i}: {parent_title}]\n{text}\n")
        return "\n---\n".join(context_parts)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # _format_sources  ── 100% UNCHANGED
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _format_sources(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format sources for frontend"""
        sources = []
        for result in search_results:
            file_name    = result.get("file_name", "")
            parent_title = result.get("parent_title", "Unknown")
            file_url     = result.get("file_url") or result.get("url")

            sources.append({
                "title": parent_title,
                "url": file_url,
                "chunk_text": result.get("text", "")[:200] + "...",
                "relevance_score": round(result.get("score", 0.0), 4),
                "metadata": {
                    "file_name": file_name,
                    "chunk_index": result.get("chunk_index", 0),
                    "parent_type": result.get("parent_type", ""),
                    "has_url": file_url is not None,
                },
            })
        return sources