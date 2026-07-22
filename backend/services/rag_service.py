import urllib.parse
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from agents.memory_agent import MemoryAgent
from agents.user_memory_agent import UserMemoryAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.retriever_agent import RetrieverAgent
from agents.query_reasoning_agent import QueryReasoningAgent
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
from config_domains import normalize_domain

# ── Import Integrated Router Modules ──
from router.taxonomy_loader import taxonomy_loader
from router.deterministic_rules import DeterministicRules
from router.keyword_scorer import KeywordScorer
from router.confuser_resolver import ConfuserResolver
from router.alias_resolver import AliasResolver
from router.thin_pointer_resolver import ThinPointerResolver
from router.co_retrieval_resolver import CoRetrievalResolver
from router.result_merger import ResultMerger

TAXONOMY_DOMAIN_TO_CANONICAL = {
    "D01_COMPANY": "selskapsrett",
    "D02_MA": "manda_fusjon_fisjon",
    "D03_ACCOUNTS": "arsregnskap_og_selskapsrapportering",
    "D04_CONTRACT": "avtalerett",
    "D05_OBLIGATIONS": "obligasjonsrett",
    "D06_DEBT": "inkasso_og_tvangsfullbyrdelse",
    "D07_INSOLVENCY": "konkursrett_og_insolvens",
    "D08_MONETARY": "pengekravsrett_fordringer",
    "D09_SECURITY": "panterett_og_sikkerhetsrett",
    "D10_DISPUTE": "tvistelosning_smb",
    "D12_EMPLOYMENT": "arbeidsrett",
    "D12_PRIVACY": "personvern_gdpr_business_compliance"
}

logger = logging.getLogger(__name__)

# Redis key template for storing reasoning context between turns
_REASONING_META_KEY = "reasoning:statute:{conversation_id}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Statute ID → Lovdata URL resolver  (unchanged from Phase 1)
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


def _is_statute_explicit(query: str) -> bool:
    """
    Detect if user explicitly named a law in the query.

    Returns True if query contains patterns like:
    - "Lov om..."
    - "LOV-"
    - "bestemmelse i"
    - "§" (section symbol)

    Returns False if statute is inferred from mechanism/domain.
    """
    if not query:
        return False

    query_lower = query.lower()
    explicit_patterns = [
        "lov om",
        "loven",
        "loven om",
        "loven for",
        "loven 20",  # LOV-YYYY format
        "lov-",
        "for-",  # FOR = forskrift
        "res-",  # RES = resolution
        "bestemmelse i",
        "kapittel",
        "§",
        "lovdatas",
        "lovdata",
    ]

    return any(pattern in query_lower for pattern in explicit_patterns)


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
        self._user_memory_agent = UserMemoryAgent(
            supabase_client=supabase_client
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
        self._router_agent = RouterAgent()
        self._doc_classifier = DocumentClassifierAgent()
        self._doc_qa_agent = DocumentQAAgent()
        # self._validation_agent = SourceValidationAgent()  # TEMPORARILY DISABLED

        logger.info(
            "[OK] RAGService initialized | "
            "retrieval=v3 (4-level fallback + BM25) | document agent active"
        )

    async def process_query(
        self,
        query: str,
        conversation_id: str,
        user_id: Optional[str] = None,
        top_k: int = 50,
        min_score: float = 0.0,
    ) -> AsyncIterator[Dict[str, Any]]:

        try:
            logger.info(f"RAGService: processing query '{query[:60]}'")

            # Quotas are now handled at the route level (chat.py)

            # ── Load history and user memory ───────────────────────────────────────────────
            history = self._orchestrator.load_history(
                conversation_id=conversation_id,
                limit=10,
            )
            user_memory = self._user_memory_agent.get_user_context(user_id) if user_id else ""
            
            if user_memory:
                logger.info("Loaded user specific cross-conversation memory")

            # ── Classify intent ────────────────────────────────────────────
            logger.info("Classifying query intent...")
            intent_result = await self._orchestrator.classify(
                query=query,
                conversation_id=conversation_id,
            )
            intent = intent_result["intent"]
            language = intent_result["language"]
            logger.info(f"Intent: {intent} | Language: {language}")

            # ── [Removed] Language override with document language ────────────
            # We no longer override query language with document language. 
            # This ensures that if a user asks in English about a Norwegian doc, 
            # they get an English response (and vice-versa), and explicit 
            # language requests in the query are honored correctly.

            yield {"type": "intent", "data": {"intent": intent, "language": language}}

            if intent == "LEGAL":
                # ── Document routing ───────────────────────────────────────
                if (
                    self._document_service
                    and self._document_service.has_documents(conversation_id)
                ):
                    logger.info(
                        "Document detected in session - routing decision needed"
                    )
                    doc_summary = self._document_service.get_doc_summary(
                        conversation_id
                    )
                    doc_class_result = await self._doc_classifier.classify(
                        query=query,
                        conversation_history=history,
                        doc_summary=doc_summary,
                    )
                    doc_intent = doc_class_result["intent"]
                    logger.info(
                        f"Document intent: {doc_intent} | "
                        f"reason='{doc_class_result.get('reason', '')}'"
                    )

                    if doc_intent == "DOCQA":
                        logger.info("Route: DOCQA (Document Only)")
                        async for event in self._handle_docqa(
                            query=query,
                            language=language,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event

                    elif doc_intent == "HYBRID":
                        logger.info("Route: HYBRID (Document + VDB)")
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
                        logger.info("Route: FOLLOWUP")
                        async for event in self._handle_followup_with_doc(
                            query=query,
                            language=language,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event

                    else:
                        logger.info("Route: LEGAL (No Document)")
                        async for event in self._handle_legal(
                            query=query,
                            language=language,
                            top_k=top_k,
                            min_score=min_score,
                            history=history,
                            conversation_id=conversation_id,
                            user_memory=user_memory,
                        ):
                            yield event
                else:
                    logger.info("No document in session - standard VDB search")
                    async for event in self._handle_legal(
                        query=query,
                        language=language,
                        top_k=top_k,
                        min_score=min_score,
                        history=history,
                        conversation_id=conversation_id,
                        user_memory=user_memory,
                    ):
                        yield event
            else:
                if (
                    self._document_service
                    and self._document_service.has_documents(conversation_id)
                ):
                    logger.info(
                        "CASUAL query but document in session — "
                        "routing through doc classifier"
                    )
                    doc_summary = self._document_service.get_doc_summary(
                        conversation_id
                    )
                    doc_class_result = await self._doc_classifier.classify(
                        query=query,
                        conversation_history=history,
                        doc_summary=doc_summary,
                    )
                    doc_intent = doc_class_result["intent"]
                    logger.info(
                        f"Doc classifier (from CASUAL): {doc_intent} | "
                        f"reason='{doc_class_result.get('reason', '')}'"
                    )

                    if doc_intent == "DOCQA":
                        async for event in self._handle_docqa(
                            query=query,
                            language=language,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event
                    elif doc_intent == "HYBRID":
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
                        async for event in self._handle_followup_with_doc(
                            query=query,
                            language=language,
                            history=history,
                            conversation_id=conversation_id,
                        ):
                            yield event
                    else:
                        # doc_intent == "LEGAL" or truly unrelated — casual is fine
                        logger.info("CASUAL query (doc present but unrelated)")
                        async for event in self._handle_casual(query, history, language, user_memory):
                            yield event
                else:
                    logger.info("CASUAL query")
                    async for event in self._handle_casual(query, history, language, user_memory):
                        yield event

        except Exception as exc:
            logger.error(
                f"[ERROR] RAGService.process_query failed | query='{query[:50]}' | {exc}",
                exc_info=True,
            )
            yield {"type": "error", "message": str(exc)}

    async def _handle_casual(
        self,
        query: str,
        history: List[Dict[str, str]],
        language: str,
        user_memory: str = "",
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("CASUAL pipeline")

        yield {"type": "sources", "data": []}

        full_answer = ""
        token_count = 0

        async for token in self._llm.generate_casual_stream(
            query=query,
            conversation_history=history,
            language=language,
            user_memory=user_memory,
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
        logger.info(f"[OK] CASUAL pipeline complete | tokens={token_count}")

    async def _handle_legal(
        self,
        query: str,
        language: str,
        top_k: int,
        min_score: float,
        history: List[Dict[str, str]],
        conversation_id: str,
        user_memory: str = "",
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("LEGAL pipeline (v6 — registry-aware + section_ref sources)")
 
        context_window = history[-9:] if history else []
 
        # ── Load previous reasoning context from Redis ─────────────────────
        previous_statute_id = None
        previous_enriched_query = None
        try:
            redis_key = _REASONING_META_KEY.format(conversation_id=conversation_id)
            reasoning_meta = self._redis.get_conversation_meta(redis_key)
            if reasoning_meta:
                previous_statute_id = reasoning_meta.get("statute_id")
                previous_enriched_query = reasoning_meta.get("enriched_query")
                logger.info(
                    f"Loaded reasoning context | "
                    f"statute_id={previous_statute_id} | "
                    f"prev_query=\'{str(previous_enriched_query)[:60]}\'"
                )
        except Exception as exc:
            logger.warning(f"[WARN] Could not read reasoning meta from Redis | {exc}")
 
        # ── [1] QueryReasoningAgent ────────────────────────────────────────
        reasoning_result = await self._reasoning_agent.run(
            query=query,
            context_window=context_window,
            previous_statute_id=previous_statute_id,
            previous_enriched_query=previous_enriched_query,
        )
        enriched_query        = reasoning_result["enriched_query"]
        primary_statute_id    = reasoning_result.get("primary_statute_id")
        secondary_statute_id  = reasoning_result.get("secondary_statute_id")
        response_style        = reasoning_result.get("response_style", "")
        domain                = reasoning_result.get("domain")
        jurisdiction          = reasoning_result.get("jurisdiction")
        statute_from_registry = reasoning_result.get("statute_from_registry", False)
 
        if domain:
            domain = normalize_domain(domain) or domain
 
        logger.info(f"Enriched query : \'{enriched_query[:80]}\'")
        logger.info(
            f"   statute={primary_statute_id} | "
            f"registry={statute_from_registry} | "
            f"domain={domain} | jurisdiction={jurisdiction} | style=\'{response_style}\'"
        )
 
        # ── [2] New Integrated Routing Pipeline ──
        # 1. Deterministic Pre-Router
        resolved_subdomain = DeterministicRules.evaluate(query)
        routing_confidence = 1.0
        routing_method = "DETERMINISTIC"

        # 2. Keyword Overlap Scorer (utilizing Norwegian concepts from QueryReasoningAgent for English query mapping)
        if not resolved_subdomain:
            key_concepts_list = []
            if primary_statute_id:
                key_concepts_list.append(primary_statute_id)
            if domain:
                key_concepts_list.append(domain)
            
            keyword_candidates = KeywordScorer.score_query(query, key_concepts=key_concepts_list)
            
            if keyword_candidates and keyword_candidates[0][1] >= 0.6:
                resolved_subdomain = keyword_candidates[0][0]
                routing_confidence = keyword_candidates[0][1]
                routing_method = "KEYWORD_OVERLAP"
                logger.info(f"Keyword Scorer selected primary subdomain: {resolved_subdomain} (confidence={routing_confidence})")
            else:
                # 3. Fallback LLM Router when keyword scoring confidence is low
                logger.info("Low keyword confidence — calling LLM RouterAgent fallback...")
                router_result = await self._router_agent.run(
                    raw_query=query,
                    enriched_query=enriched_query,
                    domain_hint=domain,
                )
                routing_confidence = router_result.get("confidence", 0.5)
                routing_method = "LLM_FALLBACK"
                resolved_subdomain = router_result.get("subdomain_candidates")[0] if router_result.get("subdomain_candidates") else None
                if not resolved_subdomain and keyword_candidates:
                    resolved_subdomain = keyword_candidates[0][0]
                    logger.info(f"LLM fallback returned None — falling back to keyword overlap candidate: {resolved_subdomain}")

        if resolved_subdomain:
            if not re.match(r"^[A-Z]{2}-\d{2}$", resolved_subdomain):
                for sub_id, sub_data in taxonomy_loader.get_all_subdomains().items():
                    if sub_data.get("name_en") == resolved_subdomain or sub_data.get("name_nb") == resolved_subdomain:
                        resolved_subdomain = sub_id
                        break

        # Initialize defaults
        final_domain = domain
        final_jurisdiction = jurisdiction
        b2b_b2c = "BOTH"
        target_subdomains = []

        if resolved_subdomain:
            # 4. Confuser Check
            resolved_subdomain = ConfuserResolver.resolve(resolved_subdomain, query)
            
            # 5. Alias Resolution
            resolved_subdomain = AliasResolver.resolve(resolved_subdomain)
            
            # 6. Thin Pointer Resolution
            subdomain_list = ThinPointerResolver.resolve(resolved_subdomain)
            
            # 7. Co-Retrieval Checks
            target_subdomains = CoRetrievalResolver.get_targets(subdomain_list, query)
            
            # Dynamic Taxonomy-based Subdomain Expansion with Stemming (only run if no subdomains resolved to avoid dilution)
            if not target_subdomains:
                expanded_subs = list(target_subdomains)
                q_words = set(re.findall(r"\b\w{4,}\b", query.lower()))
                q_stems = {w[:5] for w in q_words}
                
                for sub_id, sub_data in taxonomy_loader.get_all_subdomains().items():
                    if sub_id in expanded_subs:
                        continue
                    matched = False
                    for kw in sub_data.get("routing_keywords", []):
                        kw_words = set(re.findall(r"\b\w{4,}\b", kw.lower()))
                        kw_stems = {w[:5] for w in kw_words}
                        if q_stems.intersection(kw_stems):
                            sub_domain_family = sub_id.split("-")[0]
                            orig_families = {s.split("-")[0] for s in target_subdomains}
                            is_related = (
                                sub_domain_family in orig_families or
                                (sub_domain_family in ("CY", "IN") and any(f in ("CY", "IN") for f in orig_families))
                            )
                            if is_related:
                                expanded_subs.append(sub_id)
                                matched = True
                                break
                    if matched:
                        continue
                target_subdomains = expanded_subs
            
            # Extract metadata dynamically from taxonomy for the resolved primary subdomain
            primary_sub_data = taxonomy_loader.get_subdomain(resolved_subdomain)
            if primary_sub_data:
                taxonomy_domain_id = primary_sub_data.get("domain_id")
                final_domain = TAXONOMY_DOMAIN_TO_CANONICAL.get(taxonomy_domain_id, domain)
                
                constraints = primary_sub_data.get("routing_constraints", {})
                if constraints:
                    allowed_j = constraints.get("jurisdiction", [])
                    if allowed_j:
                        final_jurisdiction = allowed_j[0]
                    allowed_b = constraints.get("b2b_b2c", [])
                    if allowed_b:
                        b2b_b2c = allowed_b[0]

        if not target_subdomains and resolved_subdomain:
            target_subdomains = [resolved_subdomain]

        if final_domain:
            final_domain = normalize_domain(final_domain) or final_domain

        logger.info(
            f"Integrated Router Output: method={routing_method} | "
            f"primary={resolved_subdomain} | targets={target_subdomains} | "
            f"domain={final_domain} | jurisdiction={final_jurisdiction} | b2b_b2c={b2b_b2c}"
        )

        # ── Persist reasoning context ──────────────────────────────────────
        try:
            redis_key = _REASONING_META_KEY.format(conversation_id=conversation_id)
            self._redis.set_conversation_meta(
                redis_key,
                {"statute_id": primary_statute_id, "enriched_query": enriched_query},
                ttl=1800,
            )
        except Exception as exc:
            logger.warning(f"[WARN] Could not save reasoning meta to Redis | {exc}")

        # ── [3] Resolve statute → Lovdata URL ─────────────────────────────
        primary_url = _resolve_statute_url(primary_statute_id)
        secondary_url = _resolve_statute_url(secondary_statute_id)
        urls = [u for u in [primary_url, secondary_url] if u]
        statute_filter = ",".join(urls) if urls else None
        logger.info(f"statute_filter: primary={primary_statute_id}, secondary={secondary_statute_id} → '{statute_filter}'")

        # ── [4] Multi-Pass Retrieval & Deduplication ──────────────────────
        raw_retrieved_chunks = []
        
        # Execute a search pass for each target subdomain to prevent domain-level filtering issues
        for sub_candidate in (target_subdomains or [None]):
            sub_subdomain_candidates = [sub_candidate] if sub_candidate else None
            
            # Look up domain for this specific subdomain if it is co-retrieved from a different domain
            sub_domain = final_domain
            sub_urls = list(urls)
            if sub_candidate:
                sub_data = taxonomy_loader.get_subdomain(sub_candidate)
                if sub_data:
                    sub_domain_id = sub_data.get("domain_id")
                    sub_domain = TAXONOMY_DOMAIN_TO_CANONICAL.get(sub_domain_id, final_domain)
                    
                    # Union required sources for this target subdomain into statute filter
                    for req_src in sub_data.get("required_sources", []):
                        src_id = req_src.get("source_id")
                        if src_id:
                            src_url = _resolve_statute_url(src_id)
                            if src_url and src_url not in sub_urls:
                                sub_urls.append(src_url)
                                
            sub_statute_filter = ",".join(sub_urls) if sub_urls else None
            
            import time
            try:
                t0 = time.perf_counter()
                sub_results = await self._retriever_agent.run(
                    query=query,
                    enriched_query=enriched_query,
                    top_k=top_k,
                    min_score=min_score,
                    history=history,
                    statute_filter=sub_statute_filter,
                    domain=sub_domain,
                    jurisdiction=final_jurisdiction,
                    subdomain_candidates=sub_subdomain_candidates,
                    b2b_b2c=b2b_b2c,
                    statute_from_registry=statute_from_registry,
                )
                elapsed = time.perf_counter() - t0
                logger.info(f"Vector search retrieval completed in {elapsed:.4f}s for subdomain '{sub_candidate}'")
            except Exception as milvus_exc:
                logger.error(f"[ERROR] Milvus connection failure during retrieval: {milvus_exc}")
                yield {"type": "sources", "data": []}
                err_msg = (
                    "Vår søkedatabase er midlertidig utilgjengelig. Vennligst prøv igjen om et øyeblikk."
                    if language == "norwegian"
                    else "Our search database is temporarily unavailable. Please try again in a few moments."
                )
                for char in err_msg:
                    yield {"type": "token", "data": char}
                yield {
                    "type": "complete",
                    "metadata": {
                        "intent": "LEGAL",
                        "language": language,
                        "primary_statute_id": primary_statute_id,
                        "chunks_retrieved": 0,
                        "tokens_generated": len(err_msg),
                        "score": 0.0,
                        "confidence": "Error",
                        "full_answer": err_msg,
                        "rag_chunks": [],
                    },
                }
                return
            raw_retrieved_chunks.extend(sub_results)

        # Merge and deduplicate results
        search_results = ResultMerger.merge(raw_retrieved_chunks)
 
        # ── [5] Handle empty retrieval ─────────────────────────────────────
        if not search_results:
            logger.warning(
                f"[WARN] No results after 5-level fallback | "
                f"statute={primary_statute_id} | domain={final_domain}"
            )
            yield {"type": "sources", "data": []}
            no_result = (
                "Jeg finner ingen relevante lovutdrag i den tilgjengelige "
                "Lovdata-databasen som direkte svarer på dette spørsmålet."
                if language == "norwegian"
                else
                "I cannot find any relevant legal excerpts for this question."
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
                    "confidence": "No sources found",
                    "full_answer": no_result,
                    "rag_chunks": [],
                },
            }
            return
 
        # ── [6] Build RAG context ──────────────────────────────────────────
        # Reduce chunks to top 10 to prevent massive LLM context bloat and speed up TTFT
        rag_context = self._build_context(search_results[:10])
        if len(rag_context) > settings.CONTEXT_MAX_LENGTH:
            rag_context = rag_context[:settings.CONTEXT_MAX_LENGTH]
            logger.warning(f"[WARN] RAG context truncated to {settings.CONTEXT_MAX_LENGTH} chars")
 
        # ── [7] Score gate & Stream answer ────────────────────────────────
        score = 0.5
        confidence = "Partially supported by sources"
        full_answer = ""
        token_count = 0
        first_token = True

        # Check if the query asks for a specific section number
        is_specific_section_query = False
        section_nums = re.findall(r"§\s*(\d+(?:-\d+)?)", query) or re.findall(r"paragraf\s*(\d+(?:-\d+)?)", query, re.IGNORECASE)
        if section_nums:
            is_specific_section_query = True
            
        # Idea 2: Context Isolation
        # If a specific section is requested, keep ONLY the chunks matching that section
        if is_specific_section_query and search_results:
            isolated_chunks = []
            for chunk in search_results:
                chunk_section = chunk.get("section_ref") or ""
                for sec in section_nums:
                    if sec in chunk_section:
                        isolated_chunks.append(chunk)
                        break
            if isolated_chunks:
                logger.info(f"Context Isolation: filtering search results to keep only {len(isolated_chunks)} chunks for section(s) {section_nums}")
                search_results = isolated_chunks

        async for token in self._llm.generate_legal_stream(
            query=query,
            rag_context=rag_context,
            language=language,
            conversation_history=history,
            response_style=response_style,
            user_memory=user_memory,
        ):
            if first_token and token.startswith("__SCORE__"):
                first_token = False
                try:
                    score = float(token.split("__")[2])
                    confidence = _score_to_confidence(score)
                except Exception:
                    pass

                logger.info(f"Score={score} | Confidence={confidence} | chunks={len(search_results)}")

                if score < 0.5:
                    logger.warning(f"[WARN] Score={score} < 0.5 — blocking answer | statute={primary_statute_id}")
                    yield {"type": "sources", "data": []}
                    no_support = (
                        "Jeg finner ingen relevante juridiske utdrag fra min kunnskap."
                        if language == "norwegian"
                        else "I cannot find any relevant legal excerpts from my knowledge."
                    )
                    for char in no_support:
                        yield {"type": "token", "data": char}
                    yield {
                        "type": "complete",
                        "metadata": {
                            "intent": "LEGAL",
                            "language": language,
                            "primary_statute_id": primary_statute_id,
                            "chunks_retrieved": len(search_results),
                            "tokens_generated": len(no_support),
                            "score": score,
                            "confidence": confidence,
                            "full_answer": no_support,
                            "rag_chunks": [],
                        },
                    }
                    return
                else:
                    # Score is good, emit the sources
                    seen_urls = set()
                    visible_sources = []
                    for chunk in search_results:
                        base_url    = chunk.get("source_doc_url") or chunk.get("url") or ""
                        section_ref = (chunk.get("section_ref") or "").strip()
                        doc_title   = chunk.get("doc_title") or ""
                        
                        # URL encode the section reference to prevent broken space-containing URLs
                        encoded_section = urllib.parse.quote(section_ref) if section_ref else ""
                        full_url = f"{base_url}/{encoded_section}" if encoded_section else base_url
                        
                        if full_url and full_url not in seen_urls:
                            seen_urls.add(full_url)
                            visible_sources.append({
                                "url": full_url, 
                                "doc_title": doc_title, 
                                "section_ref": section_ref
                            })

                    yield {"type": "sources", "data": visible_sources}
                    logger.info(f"[OK] Emitted {len(visible_sources)} source URLs (section_ref included)")
                continue

            first_token = False
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
                "full_answer": full_answer,
                "rag_chunks": search_results,
                "detected_domain": final_domain,
            },
        }
        logger.info(
            f"[OK] LEGAL pipeline complete | "
            f"chunks={len(search_results)} | tokens={token_count} | score={score} | "
            f"fallback=L{search_results[0].get('fallback_level', 0) if search_results else 'n/a'}"
        )

    async def _handle_docqa(
        self,
        query: str,
        language: str,
        history: List[Dict[str, str]],
        conversation_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("DOCQA pipeline")

        doc_text = self._document_service.get_all_session_document_texts(
            conversation_id
        )

        if not doc_text:
            no_doc_msg = (
                "Ingen dokumenter er lastet opp i denne økten."
                if language == "norwegian"
                else "No documents have been uploaded in this session."
            )
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
                    "confidence": "No document",
                    "rag_chunks": [],
                    "tokens_generated": 0,
                },
            }
            return

        yield {"type": "sources", "data": []}

        full_answer = ""
        token_count = 0

        buffer = ""
        async for token in self._doc_qa_agent.stream_docqa(
            query=query,
            doc_text=doc_text,
            language=language,
            conversation_history=history,
        ):
            token_count += 1
            full_answer += token
            
            buffer += token
            if "[SCORE:" in buffer:
                parts = buffer.split("[SCORE:", 1)
                if parts[0]:
                    yield {"type": "token", "data": parts[0]}
                buffer = "[SCORE:" + parts[1]
            else:
                if len(buffer) > 15:
                    yield {"type": "token", "data": buffer[:-15]}
                    buffer = buffer[-15:]

        if "[SCORE:" not in buffer and buffer:
            yield {"type": "token", "data": buffer}

        # Strip [SCORE:x.x] from docqa answer
        score_pattern = re.compile(r"\[SCORE:\s*([0-9.]+)\]")
        score_match = score_pattern.search(full_answer)
        score = float(score_match.group(1)) if score_match else 0.7
        clean_answer = score_pattern.sub("", full_answer).strip()

        yield {
            "type": "complete",
            "metadata": {
                "intent": "DOCQA",
                "language": language,
                "tokens_generated": token_count,
                "score": score,
                "confidence": _score_to_confidence(score),
                "full_answer": clean_answer,
                "rag_chunks": [],
            },
        }
        logger.info(
            f"[OK] DOCQA pipeline complete | tokens={token_count} | score={score}"
        )

    async def _handle_hybrid(
        self,
        query: str,
        language: str,
        top_k: int,
        min_score: float,
        history: List[Dict[str, str]],
        conversation_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("HYBRID pipeline (Document + VDB)")

        doc_text = self._document_service.get_all_session_document_texts(
            conversation_id
        )
        if not doc_text:
            logger.warning("[WARN] HYBRID: No document text — falling back to LEGAL")
            async for event in self._handle_legal(
                query=query,
                language=language,
                top_k=top_k,
                min_score=min_score,
                history=history,
                conversation_id=conversation_id,
            ):
                yield event
            return
        search_results = await self._retriever_agent.run(
            query=query,
            enriched_query=query,
            top_k=top_k,
            min_score=min_score,
            history=history,
            statute_filter=None,
            domain=None,
            jurisdiction=None,
            subdomain_candidates=[],
            b2b_b2c="BOTH",
            statute_from_registry=False,
        )

        # Reduce chunks to top 10 to prevent massive LLM context bloat and speed up TTFT
        rag_context = self._build_context(search_results[:10]) if search_results else ""
        
        seen_urls: set = set()
        visible_sources: List[Dict[str, Any]] = []
        for chunk in (search_results or []):
            base_url    = chunk.get("source_doc_url") or chunk.get("url") or ""
            section_ref = (chunk.get("section_ref") or "").strip()
            doc_title   = chunk.get("doc_title") or ""
            
            # URL encode the section reference
            encoded_section = urllib.parse.quote(section_ref) if section_ref else ""
            full_url = f"{base_url}/{encoded_section}" if encoded_section else base_url
            
            if full_url and full_url not in seen_urls:
                seen_urls.add(full_url)
                visible_sources.append({
                    "url": full_url, 
                    "doc_title": doc_title,
                    "section_ref": section_ref
                })

        yield {"type": "sources", "data": visible_sources}

        full_answer = ""
        token_count = 0

        buffer = ""
        async for token in self._doc_qa_agent.stream_hybrid(
            query=query,
            doc_text=doc_text,
            rag_context=rag_context,
            language=language,
            conversation_history=history,
        ):
            token_count += 1
            full_answer += token
            
            buffer += token
            if "[SCORE:" in buffer:
                parts = buffer.split("[SCORE:", 1)
                if parts[0]:
                    yield {"type": "token", "data": parts[0]}
                buffer = "[SCORE:" + parts[1]
            else:
                if len(buffer) > 15:
                    yield {"type": "token", "data": buffer[:-15]}
                    buffer = buffer[-15:]

        if "[SCORE:" not in buffer and buffer:
            yield {"type": "token", "data": buffer}

        score_pattern = re.compile(r"\[SCORE:\s*([0-9.]+)\]")
        score_match = score_pattern.search(full_answer)
        score = float(score_match.group(1)) if score_match else 0.7
        clean_answer = score_pattern.sub("", full_answer).strip()

        yield {
            "type": "complete",
            "metadata": {
                "intent": "HYBRID",
                "language": language,
                "tokens_generated": token_count,
                "score": score,
                "confidence": _score_to_confidence(score),
                "full_answer": clean_answer,
                "rag_chunks": search_results,
            },
        }
        logger.info(
            f"[OK] HYBRID pipeline complete | tokens={token_count} | score={score}"
        )

    async def _handle_followup_with_doc(
        self,
        query: str,
        language: str,
        history: List[Dict[str, str]],
        conversation_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        logger.info("FOLLOWUP pipeline (context-aware, doc session)")

        # Re-use the last assistant answer as context via DOCQA
        async for event in self._handle_docqa(
            query=query,
            language=language,
            history=history,
            conversation_id=conversation_id,
        ):
            # Re-label intent so chat.py saves it correctly
            if event.get("type") == "complete":
                meta = event.get("metadata", {})
                meta["intent"] = "FOLLOWUP"
                yield {"type": "complete", "metadata": meta}
            else:
                yield event

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONTEXT BUILDER — section_ref used for human-readable citation anchor
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    
    @staticmethod
    def _build_context(chunks: List[Dict[str, Any]]) -> str:
        """
        Build the RAG context string passed to the generator.
    
        🔥 UPDATED: Excludes doc_title from the context to prevent LLM from 
        generating inline source citations like "Source: [doc_title]"
        
        The doc_title is still preserved in the chunk dict for frontend display.
    
        Uses:
        - section_ref  → human-readable citation anchor (e.g. "§ 6-1")
        - source_doc_url → full Lovdata URL for attribution header
        - text         → chunk content
        """
        parts = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk.get("text", "").strip()
            if not text:
                continue
    
            section_ref = chunk.get("section_ref") or ""
            source_url = chunk.get("source_doc_url") or chunk.get("url") or ""
            domain = chunk.get("domain") or ""
            subdomain = chunk.get("subdomain") or ""
            
            # 🔥 REMOVED: doc_title from header to prevent LLM inline citations
            # The title is still in the chunk dict for save_exchange() to use
    
            header_parts = []
            if source_url:
                header_parts.append(source_url)
            if section_ref:
                header_parts.append(section_ref)
            if domain:
                header_parts.append(domain)
            if subdomain:
                header_parts.append(subdomain)
    
            header = " | ".join(header_parts) if header_parts else f"Source {i}"
            parts.append(f"[{i}] {header}\n{text}")
    
        return "\n\n---\n\n".join(parts)
    

    async def _extract_document_summary(self, doc_text: str) -> str:
        doc_excerpt = doc_text[:2000]
        try:
            summary_prompt = (
                f"Summarize the following text in 2-3 sentences, "
                f"focusing on key topics and domains:\n\n{doc_excerpt}\n\n"
                f"Summary (max 100 words):"
            )
            summary = ""
            async for token in self._llm.generate_casual_stream(
                query=summary_prompt,
                conversation_history=[],
            ):
                summary += token
            return summary.strip()[:settings.ENRICHMENT_SUMMARY_MAX_CHARS]
        except Exception as exc:
            logger.warning(f"[WARN] Summary extraction failed | {exc}")
            return doc_text[:500]