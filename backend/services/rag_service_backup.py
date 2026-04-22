import logging
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from agents.memory_agent import MemoryAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.retriever_agent import RetrieverAgent
from agents.query_reasoning_agent import QueryReasoningAgent
from agents.reranker_agent import RerankerAgent
from agents.router_agent import RouterAgent
from agents.document_classifier_agent import DocumentClassifierAgent
from agents.document_qa_agent import DocumentQAAgent
# from agents.source_validation_agent import SourceValidationAgent  # TEMPORARILY DISABLED
from db.milvus_client import MilvusClient
from db.redis_client import RedisClient
from db.supabase_client import SupabaseClient
from services.embedding_service import EmbeddingService
from services.llm_service import LLMService, _extract_score, _score_to_confidence
from services.document_service import DocumentService
from config import settings

logger = logging.getLogger(__name__)

# Redis key template for storing reasoning context between turns
_REASONING_META_KEY = "reasoning:statute:{conversation_id}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Statute ID → Lovdata URL resolver
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_LOVDATA_BASE = "https://lovdata.no"

_TYPE_PREFIX_MAP = {
    "LOV": "lov",
    "FOR": "forskrift",
    "RES": "forskrift",
}


def _resolve_statute_url(statute_id: Optional[str]) -> Optional[str]:
    if not statute_id:
        return None

    value = statute_id.strip()

    if value.startswith("https://lovdata.no"):
        value = value.replace("/dokument/NL/lov/", "/lov/")
        value = value.replace("/dokument/SF/forskrift/", "/forskrift/")
        value = value.replace("/dokument/lov/", "/lov/")
        value = value.replace("/dokument/forskrift/", "/forskrift/")
        return value

    type_path = "lov"
    prefix_match = re.match(r"^([A-Z]+)-(.+)$", value, re.IGNORECASE)
    if prefix_match:
        prefix = prefix_match.group(1).upper()
        type_path = _TYPE_PREFIX_MAP.get(prefix, "lov")
        value = prefix_match.group(2)

    parts = value.split("-")
    if len(parts) != 4:
        logger.warning(
            f"⚠️  _resolve_statute_url: cannot parse '{statute_id}' — skipping filter"
        )
        return None

    year, month, day, number = parts
    if not all(p.isdigit() for p in parts):
        logger.warning(
            f"⚠️  _resolve_statute_url: non-numeric parts in '{statute_id}' — skipping filter"
        )
        return None

    url = f"{_LOVDATA_BASE}/{type_path}/{year}-{month}-{day}-{int(number)}"
    logger.debug(f"🗂  statute_id '{statute_id}' → URL '{url}'")
    return url


class RAGService:

    def __init__(
        self,
        llm_service: LLMService,
        milvus_client: MilvusClient,
        redis_client: RedisClient,
        supabase_client: SupabaseClient,
        embedding_service: EmbeddingService,
        document_service: Optional[DocumentService] = None,
    ) -> None:
        self._llm = llm_service
        self._milvus = milvus_client
        self._redis = redis_client
        self._supabase = supabase_client
        self._embedding = embedding_service
        self._document_service = document_service

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
        self._reranker_agent = RerankerAgent()
        self._router_agent = RouterAgent()
        self._doc_classifier = DocumentClassifierAgent()
        self._doc_qa_agent = DocumentQAAgent()
        # self._validation_agent = SourceValidationAgent()  # TEMPORARILY DISABLED

        logger.info("✅ RAGService initialized with agent routing + reasoning + reranker + document agent")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PUBLIC INTERFACE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def process_query(
        self,
        query: str,
        conversation_id: str,
        top_k: int = 50,
        min_score: float = 0.0,
    ) -> AsyncIterator[Dict[str, Any]]:

        try:
            logger.info(f"🤖 RAGService: processing query '{query[:60]}'")
            logger.debug(f"   Full query: {query}")
            logger.debug(f"   Conversation: {conversation_id}")
            logger.debug(f"   Parameters: top_k={top_k}, min_score={min_score}")

            # ── Session turn limit check ───────────────────────────────────
            # Runs before any LLM call — fast Redis check.
            # Blocks the query if the user has hit 10 turns in this 4h session.
            if self._document_service:
                turn_allowed, turns_remaining = self._document_service.check_turn_limit(
                    conversation_id
                )
                if not turn_allowed:
                    limit_msg = (
                        "Du har nådd grensen på 10 samtaler per økt (4 timer). "
                        "Økten din tilbakestilles automatisk etter 4 timer fra start."
                        "  |  "
                        "You have reached the 10-conversation limit per session (4 hours). "
                        "Your session resets automatically after 4 hours."
                    )
                    logger.warning(f"⛔ Session turn limit exceeded")
                    yield {
                        "type": "intent",
                        "data": {"intent": "BLOCKED", "language": "unknown"},
                    }
                    for char in limit_msg:
                        yield {"type": "token", "data": char}
                    yield {
                        "type": "complete",
                        "metadata": {
                            "intent": "BLOCKED",
                            "language": "unknown",
                            "full_answer": limit_msg,
                            "score": 0.0,
                            "confidence": "Session turn limit reached",
                            "rag_chunks": [],
                            "tokens_generated": 0,
                        },
                    }
                    return

                # Increment BEFORE processing so even failed turns count
                self._document_service.increment_turn_count(conversation_id)
                logger.info(
                    f"🔢 Turn {10 - turns_remaining + 1}/10 | conv={conversation_id}"
                )

            # ── Load history ───────────────────────────────────────────────
            history = self._orchestrator.load_history(
                conversation_id=conversation_id,
                limit=10,
            )
            logger.debug(f"📚 Loaded {len(history)} history messages")

            # ── Classify intent (existing IntentAgent — CASUAL / LEGAL) ───
            logger.info("🎯 Classifying query intent...")
            intent_result = await self._orchestrator.classify(
                query=query,
                conversation_id=conversation_id,
            )
            intent = intent_result["intent"]
            language = intent_result["language"]
            logger.info(f"🎯 Intent: {intent} | Language: {language}")

            yield {"type": "intent", "data": {"intent": intent, "language": language}}

            if intent == "LEGAL":
                # ── Document routing: only when a doc is present in session ──
                if (
                    self._document_service
                    and self._document_service.has_documents(conversation_id)
                ):
                    logger.info("📄 Document detected in session - routing decision needed")
                    
                    doc_summary = self._document_service.get_doc_summary(conversation_id)
                    logger.debug(f"   Document summary: {doc_summary[:100]}...")
                    
                    doc_class_result = await self._doc_classifier.classify(
                        query=query,
                        conversation_history=history,
                        doc_summary=doc_summary,
                    )
                    doc_intent = doc_class_result["intent"]
                    logger.info(
                        f"📄 Document intent: {doc_intent} | "
                        f"reason='{doc_class_result.get('reason', '')}'"
                    )
                    logger.debug(f"   🛣️ Query routing to: {doc_intent}")

                    if doc_intent == "DOCQA":
                        logger.info("↳ Route: DOCQA (Document Only - NO VDB)")
                        async for event in self._handle_docqa(
                            query=query,
                            language=language,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event

                    elif doc_intent == "HYBRID":
                        logger.info("↳ Route: HYBRID (Document + VDB)")
                        async for event in self._handle_hybrid(
                            query=query,
                            language=language,
                            top_k=top_k,
                            min_score=min_score,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event

                    elif doc_intent == "FOLLOWUP":
                        logger.info("↳ Route: FOLLOWUP (Context-Aware)")
                        async for event in self._handle_followup_with_doc(
                            query=query,
                            language=language,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event

                    else:
                        # doc_intent == "LEGAL" — no doc involvement, use existing pipeline
                        logger.info("↳ Route: LEGAL (No Document Used)")
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
                    # No document in session — existing legal pipeline, fully unchanged
                    logger.info("📋 No document in session - using standard VDB search")
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
                # CASUAL — completely unchanged
                logger.info("💬 CASUAL query detected - no RAG needed")
                async for event in self._handle_casual(query, history, language):
                    yield event

        except Exception as exc:
            logger.error(
                f"❌ RAGService.process_query failed | query='{query[:50]}' | {exc}",
                exc_info=True,
            )
            yield {"type": "error", "message": str(exc)}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # QUERY ENRICHMENT HELPERS (Phase 2: Enhanced VDB Search)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _extract_document_summary(self, doc_text: str) -> str:
        """
        Extract a concise summary from document text using LLM.
        
        Returns: Summary string (max 500 characters)
        """
        logger.debug("📄 Extracting document summary...")
        
        # Truncate to first 2000 chars for summary extraction
        doc_excerpt = doc_text[:2000]
        
        try:
            summary_prompt = (
                f"Summarize the following text in 2-3 sentences, focusing on key topics and domains:\n\n"
                f"{doc_excerpt}\n\n"
                f"Summary (max 100 words):"
            )
            
            summary = ""
            async for token in self._llm.generate_casual_stream(
                query=summary_prompt,
                conversation_history=[]
            ):
                summary += token
            
            summary = summary.strip()[:settings.ENRICHMENT_SUMMARY_MAX_CHARS]
            logger.debug(f"✅ Summary extracted ({len(summary)} chars): {summary[:100]}...")
            return summary
        except Exception as exc:
            logger.warning(f"⚠️  Summary extraction failed, using first 500 chars | {exc}")
            return doc_text[:500]

    async def _enrich_query_with_document(
        self,
        user_query: str,
        doc_text: str,
        conversation_id: str
    ) -> str:
        """
        Enrich user query with document context for better VDB retrieval.
        
        Process:
        1. Extract document summary
        2. Identify key entity/keyword candidates
        3. Blend summary context with original query
        
        Returns: Enriched query string
        """
        logger.debug(f"⚡ Enriching query with document context...")
        logger.debug(f"   Original query: '{user_query}'")
        
        # Extract summary
        doc_summary = await self._extract_document_summary(doc_text)
        logger.debug(f"   Document summary: {doc_summary[:100]}...")
        
        # Extract key keywords from summary/document
        # Simple approach: take first N words from summary
        summary_words = doc_summary.split()[:settings.ENRICHMENT_KEYWORDS_COUNT]
        keywords = " ".join(summary_words)
        
        # Create enriched query
        enriched_query = f"{user_query} [{keywords}]"
        
        logger.debug(f"   Enriched query: '{enriched_query}'")
        logger.info(
            f"⚡ Query enriched | original={len(user_query)} chars | "
            f"enriched={len(enriched_query)} chars | conv={conversation_id}"
        )
        
        return enriched_query

    async def _handle_enriched_vdb_search(
        self,
        query: str,
        doc_summary: str,
        language: str,
        top_k: int = 5,
        min_score: float = 0.0,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Handle ENRICHED_VDB pipeline:
        1. Enrich query with document summary
        2. Search Milvus VDB
        3. Return top-k results with scores
        
        Used when explicit enriched query scenario is triggered.
        """
        logger.info(f"🔀 ENRICHED_VDB pipeline starting...")
        logger.debug(f"   Document summary: {doc_summary[:100]}...")
        
        # Create enriched query from user query + document summary
        enriched_query = f"{query} Context: {doc_summary}"
        
        logger.debug(f"   Enriched query: {enriched_query}")
        
        # Embed the enriched query
        try:
            enriched_embedding = self._embedding.embed_text(enriched_query)
            logger.debug(f"✅ Enriched query embedded")
        except Exception as exc:
            logger.error(f"❌ Failed to embed enriched query | {exc}")
            yield {"type": "error", "message": f"Embedding failed: {exc}"}
            return
        
        # Search Milvus with enriched query
        try:
            logger.debug(f"   Searching Milvus with enriched query (top_k={top_k})...")
            results = self._milvus.search(
                query_embedding=enriched_embedding,
                top_k=top_k,
                metric_type="L2",
            )
            logger.info(f"🔍 Enriched search returned {len(results)} results")
        except Exception as exc:
            logger.error(f"❌ Milvus search failed | {exc}")
            yield {"type": "error", "message": f"VDB search failed: {exc}"}
            return
        
        # Format results
        formatted_results = []
        for result in results:
            meta = result.get("metadata", {})
            score = result.get("score", 0.0)
            
            if score >= min_score:
                formatted_results.append({
                    "content": result.get("content", ""),
                    "metadata": meta,
                    "score": score,
                    "statute_url": _resolve_statute_url(meta.get("statute_id")),
                })
                logger.debug(
                    f"   ✓ Result: score={score:.3f} | "
                    f"statute={meta.get('statute_id', 'N/A')}"
                )
        
        logger.info(
            f"✨ Enriched VDB search complete | "
            f"found={len(formatted_results)} relevant chunks"
        )
        
        # Yield sources and results
        yield {
            "type": "sources",
            "data": [
                {
                    "type": "statute",
                    "statute_id": r["metadata"].get("statute_id"),
                    "statute_url": r["statute_url"],
                    "score": r["score"],
                }
                for r in formatted_results
            ]
        }
        
        # Yield individual results
        for result in formatted_results:
            yield {
                "type": "chunk",
                "data": {
                    "content": result["content"],
                    "score": result["score"],
                    "statute": result["metadata"].get("statute_id"),
                }
            }
        
        yield {
            "type": "complete",
            "metadata": {
                "intent": "ENRICHED_VDB",
                "language": language,
                "results_count": len(formatted_results),
                "full_answer": "[Enriched VDB search results shown above]",
                "rag_chunks": formatted_results,
            },
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CASUAL PIPELINE  — UNCHANGED
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
    # LEGAL PIPELINE — UNCHANGED
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

        context_window = history[-9:] if history else []

        previous_statute_id = None
        previous_enriched_query = None
        try:
            redis_key = _REASONING_META_KEY.format(conversation_id=conversation_id)
            reasoning_meta = self._redis.get_conversation_meta(redis_key)
            if reasoning_meta:
                previous_statute_id     = reasoning_meta.get("statute_id")
                previous_enriched_query = reasoning_meta.get("enriched_query")
                logger.info(
                    f"📖 Loaded reasoning context | "
                    f"statute_id={previous_statute_id} | "
                    f"prev_query='{str(previous_enriched_query)[:60]}'"
                )
        except Exception as exc:
            logger.warning(f"⚠️  Could not read reasoning meta from Redis | {exc}")

        reasoning_result = await self._reasoning_agent.run(
            query=query,
            context_window=context_window,
            previous_statute_id=previous_statute_id,
            previous_enriched_query=previous_enriched_query,
        )
        enriched_query     = reasoning_result["enriched_query"]
        primary_statute_id = reasoning_result.get("primary_statute_id")
        response_style     = reasoning_result.get("response_style", "")
        domain             = reasoning_result.get("domain")
        jurisdiction       = reasoning_result.get("jurisdiction")

        logger.info(
            f"🧠 Enriched query: '{enriched_query}' | style='{response_style}' | "
            f"domain={domain} | jurisdiction={jurisdiction}"
        )

        router_result = await self._router_agent.run(
            raw_query=query,
            enriched_query=enriched_query,
            domain_hint=domain,
        )
        final_domain         = domain or router_result.get("domain") or None
        final_jurisdiction   = jurisdiction or router_result.get("jurisdiction") or None
        subdomain_candidates = router_result.get("subdomain_candidates") or []
        logger.info(
            f"🔀 Router: domain={final_domain} | subdomains={subdomain_candidates} | "
            f"b2b_b2c={router_result.get('b2b_b2c')} | "
            f"jurisdiction={final_jurisdiction} | "
            f"confidence={router_result.get('confidence')}"
        )

        try:
            redis_key = _REASONING_META_KEY.format(conversation_id=conversation_id)
            self._redis.set_conversation_meta(
                redis_key,
                {
                    "statute_id":     primary_statute_id,
                    "enriched_query": enriched_query,
                },
                ttl=1800,
            )
            logger.info(f"💾 Saved reasoning context | statute_id={primary_statute_id}")
        except Exception as exc:
            logger.warning(f"⚠️  Could not save reasoning meta to Redis | {exc}")

        statute_filter = _resolve_statute_url(primary_statute_id)
        logger.info(
            f"🗂  statute_filter resolved: '{primary_statute_id}' → '{statute_filter}'"
        )

        search_results, validation_passed = await self._retrieve_and_validate(
            enriched_query=enriched_query,
            reasoning_summary=enriched_query,
            top_k=top_k,
            min_score=min_score,
            history=history,
            language=language,
            statute_filter=statute_filter,
            domain=final_domain,
            jurisdiction=final_jurisdiction,
            original_query=query,
        )

        if not validation_passed:
            logger.warning("⚠️  Source validation failed after 2 attempts — returning not-found")
            logger.warning(
                "📋 MISSING_COVERAGE | reason=validation_failed | "
                f"query='{query}' | enriched_query='{enriched_query}' | "
                f"statute_id='{primary_statute_id}' | domain={domain} | "
                f"jurisdiction={jurisdiction} | language={language}"
            )
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
            logger.warning(
                "📋 MISSING_COVERAGE | reason=no_milvus_results | "
                f"query='{query}' | enriched_query='{enriched_query}' | "
                f"statute_id='{primary_statute_id}' | domain={domain} | "
                f"jurisdiction={jurisdiction} | language={language}"
            )
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
        score         = score_result["score"]
        confidence    = score_result["confidence"]
        scored_answer = score_result["answer"]

        logger.info(f"📊 Score={score} | Confidence={confidence}")

        visible_sources = []
        visible_chunks  = []

        if score >= 0.5:
            visible_chunks  = search_results
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
    # DOCQA PIPELINE — answers from uploaded document ONLY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _handle_docqa(
        self,
        query: str,
        language: str,
        history: List[Dict[str, str]],
        conversation_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("📄 DOCQA pipeline - Document-Only Processing")
        logger.debug(f"   Query: '{query}'")
        logger.debug(f"   Language: {language}")
        logger.debug(f"   Conversation: {conversation_id}")
        logger.debug(f"   ℹ️  NO VDB ACCESS - Using document text only")

        doc_text = self._document_service.get_all_session_document_texts(conversation_id)
        
        if doc_text:
            logger.debug(f"   📚 Document loaded: {len(doc_text)} characters")
        else:
            logger.debug(f"   ⚠️  Empty document text")

        if not doc_text:
            no_doc_msg = (
                "Ingen dokumenter er lastet opp i denne økten."
                if language == "norwegian"
                else "No documents are uploaded in this session."
            )
            logger.warning("📄 No document found in session")
            yield {"type": "sources", "data": []}
            for char in no_doc_msg:
                yield {"type": "token", "data": char}
            yield {
                "type": "complete",
                "metadata": {
                    "intent": "DOCQA",
                    "language": language,
                    "full_answer": no_doc_msg,
                    "score": 0.0,
                    "confidence": "No document found",
                    "rag_chunks": [],
                    "tokens_generated": 0,
                },
            }
            return

        yield {"type": "sources", "data": []}
        logger.info("🔄 Generating DOCQA response from document...")

        full_answer = ""
        token_count = 0
        score_re    = re.compile(r"\[SCORE:[0-9.]+\]")
        buffer      = ""

        async for token in self._doc_qa_agent.stream_docqa(
            query=query,
            doc_text=doc_text,
            language=language,
            conversation_history=history,
        ):
            token_count += 1
            buffer += token

            if score_re.search(buffer):
                clean = score_re.split(buffer)[0].rstrip("\n")
                if clean:
                    full_answer += clean
                    yield {"type": "token", "data": clean}
                break

            if len(buffer) > 15:
                chunk = buffer[:-15]
                full_answer += chunk
                yield {"type": "token", "data": chunk}
                buffer = buffer[-15:]

        if buffer:
            clean = score_re.sub("", buffer).rstrip("\n")
            if clean:
                full_answer += clean
                yield {"type": "token", "data": clean}

        scored_answer, score = _extract_score(full_answer)
        confidence = _score_to_confidence(score)
        
        logger.debug(f"   ✅ Response generated: {token_count} tokens, score={score:.2f}")
        logger.info(f"✅ DOCQA complete | Score: {score:.2f} ({confidence})")

        yield {
            "type": "complete",
            "metadata": {
                "intent": "DOCQA",
                "language": language,
                "tokens_generated": token_count,
                "score": score,
                "confidence": confidence,
                "full_answer": scored_answer,
                "rag_chunks": [],
            },
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HYBRID PIPELINE — document text + Milvus chunks in one prompt
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _handle_hybrid(
        self,
        query: str,
        language: str,
        top_k: int,
        min_score: float,
        history: List[Dict[str, str]],
        conversation_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("🔀 HYBRID pipeline")

        # ── Step 1: Get document text ────────────────────────────────────
        doc_text = self._document_service.get_all_session_document_texts(conversation_id)

        # ── Step 2: Enrich query via reasoning agent (same as legal) ────
        context_window          = history[-9:] if history else []
        previous_statute_id     = None
        previous_enriched_query = None

        try:
            redis_key      = _REASONING_META_KEY.format(conversation_id=conversation_id)
            reasoning_meta = self._redis.get_conversation_meta(redis_key)
            if reasoning_meta:
                previous_statute_id     = reasoning_meta.get("statute_id")
                previous_enriched_query = reasoning_meta.get("enriched_query")
        except Exception as exc:
            logger.warning(f"⚠️ Could not read reasoning meta | {exc}")

        # Feed a preview of the document to the reasoning agent so it can
        # identify which law is most relevant to this specific contract/doc
        doc_context_hint     = (
            f"\n\nUploaded document preview:\n{doc_text[:800]}" if doc_text else ""
        )
        enriched_query_input = query + doc_context_hint

        reasoning_result   = await self._reasoning_agent.run(
            query=enriched_query_input,
            context_window=context_window,
            previous_statute_id=previous_statute_id,
            previous_enriched_query=previous_enriched_query,
        )
        enriched_query     = reasoning_result["enriched_query"]
        primary_statute_id = reasoning_result.get("primary_statute_id")
        domain             = reasoning_result.get("domain")
        jurisdiction       = reasoning_result.get("jurisdiction")

        # Save reasoning context for follow-up turns
        try:
            redis_key = _REASONING_META_KEY.format(conversation_id=conversation_id)
            self._redis.set_conversation_meta(
                redis_key,
                {"statute_id": primary_statute_id, "enriched_query": enriched_query},
                ttl=1800,
            )
        except Exception as exc:
            logger.warning(f"⚠️ Could not save reasoning meta | {exc}")

        statute_filter = _resolve_statute_url(primary_statute_id)

        # ── Step 3: Retrieve from Milvus ─────────────────────────────────
        search_results, _ = await self._retrieve_and_validate(
            enriched_query=enriched_query,
            reasoning_summary=enriched_query,
            top_k=top_k,
            min_score=min_score,
            history=history,
            language=language,
            statute_filter=statute_filter,
            domain=domain,
            jurisdiction=jurisdiction,
            original_query=query,
        )

        rag_context = self._build_context(search_results) if search_results else ""

        # ── Step 4: Emit sources ─────────────────────────────────────────
        if search_results:
            visible_sources = list({
                r.get("url") or r.get("statute_id") or r.get("file_name")
                for r in search_results
                if r.get("url") or r.get("statute_id") or r.get("file_name")
            })
            yield {"type": "sources", "data": visible_sources}
            logger.info(f"✅ HYBRID: emitting {len(visible_sources)} source URLs")
        else:
            yield {"type": "sources", "data": []}
            logger.warning("⚠️ HYBRID: No Milvus results — will answer from document only")

        # ── Step 5: Stream combined answer ───────────────────────────────
        full_answer = ""
        token_count = 0
        score_re    = re.compile(r"\[SCORE:[0-9.]+\]")
        buffer      = ""

        async for token in self._doc_qa_agent.stream_hybrid(
            query=query,
            doc_text=doc_text or "(no document text available)",
            rag_context=rag_context or "(no legal sources retrieved)",
            language=language,
            conversation_history=history,
        ):
            token_count += 1
            buffer += token

            if score_re.search(buffer):
                clean = score_re.split(buffer)[0].rstrip("\n")
                if clean:
                    full_answer += clean
                    yield {"type": "token", "data": clean}
                break

            if len(buffer) > 15:
                chunk = buffer[:-15]
                full_answer += chunk
                yield {"type": "token", "data": chunk}
                buffer = buffer[-15:]

        if buffer:
            clean = score_re.sub("", buffer).rstrip("\n")
            if clean:
                full_answer += clean
                yield {"type": "token", "data": clean}

        scored_answer, score = _extract_score(full_answer)
        confidence = _score_to_confidence(score)

        yield {
            "type": "complete",
            "metadata": {
                "intent": "HYBRID",
                "language": language,
                "primary_statute_id": primary_statute_id,
                "chunks_retrieved": len(search_results),
                "tokens_generated": token_count,
                "score": score,
                "confidence": confidence,
                "full_answer": scored_answer,
                "rag_chunks": search_results,
            },
        }
        logger.info(
            f"✅ HYBRID pipeline complete | chunks={len(search_results)} | "
            f"tokens={token_count} | score={score}"
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FOLLOWUP PIPELINE — continues prior doc/legal thread using memory
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _handle_followup_with_doc(
        self,
        query: str,
        language: str,
        history: List[Dict[str, str]],
        conversation_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("🔄 FOLLOWUP (doc session) pipeline")

        # Inject a short doc reminder so the model retains document knowledge
        doc_text    = self._document_service.get_latest_document_text(conversation_id)
        doc_reminder = ""
        if doc_text:
            doc_reminder = (
                f"[Context: the user has an uploaded document in this session. "
                f"Document preview (first 300 chars): {doc_text[:300]}...]\n\n"
            )

        enriched_query = f"{doc_reminder}{query}" if doc_reminder else query

        yield {"type": "sources", "data": []}

        full_answer = ""
        token_count = 0

        async for token in self._llm.generate_casual_stream(
            query=enriched_query,
            conversation_history=history,
        ):
            token_count += 1
            full_answer += token
            yield {"type": "token", "data": token}

        yield {
            "type": "complete",
            "metadata": {
                "intent": "FOLLOWUP",
                "language": language,
                "tokens_generated": token_count,
                "score": 1.0,
                "confidence": "Follow-up from document session",
                "full_answer": full_answer,
                "rag_chunks": [],
            },
        }
        logger.info(f"✅ FOLLOWUP pipeline complete | tokens={token_count}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Dynamic query reformulation — UNCHANGED
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
            response     = await self._llm._llm.agenerate([messages])
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
    # Retrieve + Rerank + (Validate DISABLED temporarily) — UNCHANGED
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
        domain: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        original_query: Optional[str] = None,
    ):
        retrieval_query     = enriched_query
        active_filter       = statute_filter
        active_domain       = domain
        active_jurisdiction = jurisdiction

        for attempt in (1, 2):
            logger.info(
                f"🔎 RetrieverAgent attempt {attempt} | "
                f"query='{retrieval_query[:80]}' | statute_filter='{active_filter}' | "
                f"domain='{active_domain}' | jurisdiction='{active_jurisdiction}'"
            )

            raw_results = await self._retriever_agent.run(
                query=retrieval_query,
                top_k=settings.RERANKER_RECALL_TOP_K,
                min_score=0.0,
                history=history,
                statute_filter=active_filter,
                domain=active_domain,
                jurisdiction=active_jurisdiction,
            )

            logger.info(
                f"📦 Retrieved {len(raw_results)} raw chunks (attempt {attempt}) | "
                f"file_filter='{active_filter}'"
            )

            if not raw_results:
                if attempt == 1:
                    logger.warning(
                        f"⚠️  Zero results on attempt 1 | filter='{active_filter}' | "
                        f"domain='{active_domain}'. "
                        "Dropping all filters and reformulating for attempt 2..."
                    )
                    active_filter       = None
                    active_domain       = None
                    active_jurisdiction = None
                    retrieval_query = await self._reformulate_query_with_llm(
                        reasoning_summary=reasoning_summary,
                        original_query=enriched_query,
                        chunks=[],
                    )
                    continue
                else:
                    logger.warning("⚠️  Zero results on attempt 2 — terminal failure")
                    return [], False

            reranked = self._reranker_agent.rerank(
                query=retrieval_query,
                chunks=raw_results,
                top_k=settings.RERANKER_FINAL_TOP_K,
            )

            if not reranked:
                logger.warning(f"⚠️  Reranker returned empty list (attempt {attempt})")
                return [], False

            best_score = reranked[0].get("rerank_score", 0.0)

            if best_score < settings.RERANKER_MIN_SCORE:
                logger.warning(
                    f"⚠️  Reranker quality gate failed (attempt {attempt}) | "
                    f"best={best_score:.4f} < threshold={settings.RERANKER_MIN_SCORE} | "
                    f"filter='{active_filter}'"
                )
                if attempt == 1:
                    logger.info(
                        "🔄 Dropping statute_filter + domain and reformulating for attempt 2..."
                    )
                    active_filter       = None
                    active_domain       = None
                    active_jurisdiction = None
                    retrieval_query = await self._reformulate_query_with_llm(
                        reasoning_summary=reasoning_summary,
                        original_query=enriched_query,
                        chunks=raw_results,
                    )
                    continue
                else:
                    logger.warning(
                        "⚠️  Reranker quality gate failed on attempt 2 — returning empty"
                    )
                    return [], False

            search_results = reranked

            logger.info(
                f"🔃 After reranking: {len(search_results)} chunks passed to generation | "
                f"top rerank_score={best_score:.4f}"
            )
            for i, chunk in enumerate(search_results[:5], start=1):
                logger.info(
                    f"""
                    🧾 RERANKED #{i}
                    Title: {chunk.get('parent_title')}
                    File: {chunk.get('file_name')}
                    Rerank Score: {chunk.get('rerank_score')}
                    Preview: {chunk.get('text', '')[:300]}
                    """
                )

            # Validation bypassed — return reranked results directly
            return search_results, True

        return [], False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS — UNCHANGED
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_context(self, search_results: List[Dict[str, Any]]) -> str:
        parts = []
        for i, result in enumerate(search_results, start=1):
            title = result.get("parent_title", "Unknown")
            text  = result.get("text", "")
            parts.append(f"[Kilde {i}: {title}]\n{text}\n")
        return "\n---\n".join(parts)

    def _format_sources(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sources = []
        for result in search_results:
            url = result.get("url") or result.get("file_url")
            sources.append({
                "title":           result.get("parent_title", "Unknown"),
                "url":             url,
                "chunk_text":      result.get("text", "")[:200] + "...",
                "relevance_score": round(result.get("score", 0.0), 4),
                "metadata": {
                    "file_name":   result.get("file_name", ""),
                    "chunk_index": result.get("chunk_index", 0),
                    "parent_type": result.get("parent_type", ""),
                },
            })
        return sources