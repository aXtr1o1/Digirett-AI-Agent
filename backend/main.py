"""
Lovdata RAG System - FastAPI Backend
WITH LANGUAGE FIX - Fully Working Version
"""
import uuid
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import logging
import time
from typing import Optional, Union
import json

from .config import settings
from .models import (
    ChatRequest, 
    ChatResponse, 
    SearchRequest, 
    SearchResponse,
    HealthResponse,
    FeedbackRequest
)
from .services.milvus_service import MilvusService
from .services.embedding_service import EmbeddingService
from .services.fireworks_service import FireworksService
from .services.cache_service import CacheService
from .utils.logger import setup_enhanced_logger
from .utils.metrics import MetricsCollector

# Setup logging
logger = setup_enhanced_logger(__name__)
metrics = MetricsCollector()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Services
milvus_service: Optional[MilvusService] = None
embedding_service: Optional[EmbeddingService] = None
llm_service: Optional[FireworksService] = None
cache_service: Optional[CacheService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global milvus_service, embedding_service, llm_service, cache_service
    
    logger.info("Starting Lovdata RAG System...")
    
    try:
        logger.info("Initializing Milvus service...")
        milvus_service = MilvusService(
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
            collection_name=settings.MILVUS_COLLECTION
        )
        
        logger.info("Initializing Embedding service...")
        embedding_service = EmbeddingService()
        
        logger.info("Initializing Fireworks/Azure service...")
        llm_service = FireworksService(
            api_key=settings.Key,
            model=settings.Model_Name,
            Target_url=settings.Target_URI
        )
        logger.info("Azure model Initialized")
        
        logger.info("Initializing Cache service...")
        cache_service = CacheService()
        
        logger.info("All services initialized successfully!")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    finally:
        logger.info("Shutting down services...")
        if milvus_service:
            milvus_service.close()
        if cache_service:
            cache_service.close()
        logger.info("Shutdown complete")


app = FastAPI(
    title="Lovdata RAG API",
    description="RAG system with Language Fix and Intent Detection",
    version="2.2.0",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests"""
    start_time = time.time()
    
    logger.info(f"Request: {request.method} {request.url.path}")
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        
        metrics.record_request(
            endpoint=request.url.path,
            method=request.method,
            status_code=response.status_code,
            duration=process_time
        )
        
        response.headers["X-Process-Time"] = str(process_time)
        
        logger.info(f"Response: {request.method} {request.url.path} - {response.status_code} ({process_time:.2f}s)")
        
        return response
        
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"Error: {request.method} {request.url.path} - {e} ({process_time:.2f}s)")
        metrics.record_error(endpoint=request.url.path, error_type=type(e).__name__)
        raise


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Check system health"""
    try:
        milvus_status = milvus_service.check_connection()
        llm_status = await llm_service.check_connection()
        cache_status = cache_service.is_connected()
        
        return HealthResponse(
            status="healthy" if all([milvus_status, llm_status, cache_status]) else "degraded",
            version="2.2.0",
            milvus_connected=milvus_status,
            llm_connected=llm_status,
            cache_connected=cache_status,
            total_queries=metrics.get_total_queries(),
            uptime=metrics.get_uptime()
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unhealthy: {str(e)}"
        )


@app.post("/chat", response_model=ChatResponse, tags=["RAG"])
@limiter.limit("250/minute")
async def chat(request: Request, chat_request: ChatRequest):
    """
    Ask a question with language-aware responses
    Sources shown only when score >= 0.5
    """
    start_time = time.time()
    
    try:
        logger.info(f"Chat request: {chat_request.query[:100]}...")
        
        # Step 1: Detect intent using improved language detection
        intent_result = await llm_service.detect_intent(chat_request.query)
        intent = intent_result["intent"]
        language = intent_result["language"]
        
        logger.info(f"[DETECTION] Intent: {intent}, Language: {language}")
        
        # Step 2: If CASUAL → Skip Milvus, generate free response
        if intent == "CASUAL":
            logger.info("CASUAL query detected - skipping Milvus retrieval")
            
            answer, tokens_used = await llm_service.generate_casual_response(
                query=chat_request.query,
                language=language
            )
            
            return ChatResponse(
                answer=answer,
                sources=[],
                metadata={
                    "query_time": time.time() - start_time,
                    "chunks_retrieved": 0,
                    "tokens_used": tokens_used,
                    "cached": False,
                    "language": language,
                    "intent": "CASUAL",
                    "model": settings.Model_Name,
                    "score": 1.0,
                    "confidence": "Casual conversation"
                }
            )
        
        # Step 3: LEGAL query → Proceed with Milvus retrieval
        logger.info("LEGAL query detected - proceeding with Milvus retrieval")
        
        # Check cache
        cache_key = cache_service.generate_cache_key(
            chat_request.query, 
            chat_request.top_k
        )
        
        cached_response = cache_service.get(cache_key)
        if cached_response:
            logger.info("Cache hit!")
            cached_response["metadata"]["cached"] = True
            cached_response["metadata"]["language"] = language
            return ChatResponse(**cached_response)
        
        # Generate embedding
        logger.info("Generating query embedding...")
        query_embedding = await embedding_service.embed_query(chat_request.query)
        
        # Search Milvus
        logger.info(f"Searching Milvus for top-{chat_request.top_k} chunks...")
        search_results = milvus_service.search(
            embedding=query_embedding,
            top_k=chat_request.top_k
        )
        
        if not search_results:
            logger.warning("No search results from Milvus")
            
            no_result_msg = (
                "Jeg finner ingen relevante lovutdrag i den tilgjengelige Lovdata-databasen som direkte svarer på dette spørsmålet."
                if language == "norwegian"
                else "I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question."
            )
            
            return ChatResponse(
                answer=no_result_msg,
                sources=[],
                metadata={
                    "query_time": time.time() - start_time,
                    "chunks_retrieved": 0,
                    "tokens_used": 0,
                    "cached": False,
                    "language": language,
                    "intent": "LEGAL",
                    "score": 0.1,
                    "confidence": "No sources found"
                }
            )
        
        # Build context
        logger.info("Building context...")
        context = _build_context(search_results)
        
        # Generate legal answer WITH SCORING and LANGUAGE FIX
        logger.info(f"Generating legal answer in {language}...")
        result = await llm_service.generate_legal_answer(
            query=chat_request.query,
            context=context,
            language=language,
            temperature=chat_request.temperature
        )
        
        answer = result["answer"]
        score = result["score"]
        confidence = result["confidence"]
        tokens_used = result["tokens_used"]
        
        logger.info(f"[SUCCESS] Answer generated - Score: {score}, Confidence: {confidence}, Language: {language}")
        
        # Only show sources if score >= 0.5
        if score >= 0.5:
            logger.info(f"[INFO] Score {score} >= 0.5: Showing sources")
            sources = (
                _format_sources_from_milvus(search_results)
                if chat_request.include_sources
                else []
            )
        else:
            logger.info(f"[WARNING] Score {score} < 0.5: Hiding sources")
            sources = []
        
        response_data = {
            "answer": answer,
            "sources": sources,
            "metadata": {
                "query_time": time.time() - start_time,
                "chunks_retrieved": len(search_results),
                "tokens_used": tokens_used,
                "cached": False,
                "language": language,
                "intent": "LEGAL",
                "model": settings.Model_Name,
                "score": score,
                "confidence": confidence
            }
        }
        
        cache_service.set(cache_key, response_data, ttl=3600)
        
        logger.info(f"Answer generated in {response_data['metadata']['query_time']:.2f}s")
        
        return ChatResponse(**response_data)
        
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        metrics.record_error(endpoint="/chat", error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process query: {str(e)}"
        )


@app.post("/chat/stream", tags=["RAG"])
@limiter.limit("250/minute")
async def chat_stream(request: Request, chat_request: ChatRequest):
    """
    Stream answer with language-aware responses
    """
    
    async def generate_stream():
        try:
            logger.info(f"Streaming chat request: {chat_request.query[:100]}...")
            
            # Step 1: Detect intent with improved language detection
            intent_result = await llm_service.detect_intent(chat_request.query)
            intent = intent_result["intent"]
            language = intent_result["language"]
            
            logger.info(f"[STREAM] Intent: {intent}, Language: {language}")
            
            # Step 2: If CASUAL → Stream without Milvus
            if intent == "CASUAL":
                logger.info("CASUAL query - streaming without sources")
                
                yield f"data: {json.dumps({'type': 'sources', 'data': []})}\n\n"
                
                token_count = 0
                async for token in llm_service.generate_answer_stream(
                    query=chat_request.query,
                    context="",
                    language=language,
                    temperature=0.3,
                    intent=intent
                ):
                    token_count += 1
                    yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"
                
                yield f"data: {json.dumps({'type': 'complete', 'metadata': {'intent': 'CASUAL', 'language': language, 'tokens_generated': token_count, 'score': 1.0, 'confidence': 'Casual conversation'}})}\n\n"
                return
            
            # Step 3: LEGAL query → Use Milvus
            logger.info("LEGAL query - retrieving from Milvus")
            
            query_embedding = await embedding_service.embed_query(chat_request.query)
            
            search_results = milvus_service.search(
                embedding=query_embedding,
                top_k=chat_request.top_k
            )
            
            if not search_results:
                yield f"data: {json.dumps({'type': 'sources', 'data': []})}\n\n"
                
                no_result_msg = (
                    "Jeg finner ingen relevante lovutdrag i den tilgjengelige Lovdata-databasen som direkte svarer på dette spørsmålet."
                    if language == "norwegian"
                    else "I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question."
                )
                
                for char in no_result_msg:
                    yield f"data: {json.dumps({'type': 'token', 'data': char})}\n\n"
                
                yield f"data: {json.dumps({'type': 'complete', 'metadata': {'intent': 'LEGAL', 'language': language, 'chunks_retrieved': 0, 'score': 0.1, 'confidence': 'No sources found'}})}\n\n"
                return
            
            # Build context
            context = _build_context(search_results)
            
            # Stream the answer in correct language
            full_answer = ""
            token_count = 0
            
            async for token in llm_service.generate_answer_stream(
                query=chat_request.query,
                context=context,
                language=language,
                temperature=chat_request.temperature,
                intent=intent
            ):
                token_count += 1
                full_answer += token
                yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"
            
            # Evaluate score
            if "cannot find" in full_answer.lower() or "ingen relevante" in full_answer.lower():
                score = 0.1
                confidence = "Not supported by sources"
            elif "partially" in full_answer.lower() or "delvis" in full_answer.lower():
                score = 0.6
                confidence = "Partially covered in sources"
            else:
                score = 0.9
                confidence = "Fully supported by sources"
            
            logger.info(f"[SUCCESS] Streaming complete - Score: {score}, Language: {language}")
            
            # Only send sources if score >= 0.5
            if score >= 0.5:
                logger.info(f"[INFO] Score {score} >= 0.5: Sending sources")
                sources = _format_sources_from_milvus(search_results)
                yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"
            else:
                logger.info(f"[WARNING] Score {score} < 0.5: Not sending sources")
                yield f"data: {json.dumps({'type': 'sources', 'data': []})}\n\n"
            
            # Send completion metadata
            metadata = {
                "type": "complete",
                "metadata": {
                    "intent": "LEGAL",
                    "chunks_retrieved": len(search_results),
                    "tokens_generated": token_count,
                    "language": language,
                    "model": settings.Model_Name,
                    "score": score,
                    "confidence": confidence
                }
            }
            yield f"data: {json.dumps(metadata)}\n\n"
            
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# Helper Functions

def _build_context(search_results: list) -> str:
    """Build context from Milvus results"""
    context_parts = []
    
    for i, result in enumerate(search_results, 1):
        parent_title = result.get('parent_title', 'Unknown')
        text = result.get('text', '')
        
        context_parts.append(f"[Kilde {i}: {parent_title}]\n{text}\n")
    
    return "\n---\n".join(context_parts)


def _format_sources_from_milvus(search_results: list) -> list:
    """Format sources from Milvus metadata"""
    sources = []
    
    for result in search_results:
        file_name = result.get('file_name', '')
        parent_title = result.get('parent_title', 'Unknown')
        
        file_url = result.get('url') or result.get('file_url')
        
        if not file_url:
            logger.warning(f"No URL in Milvus for: {file_name}")
            file_url = _construct_lovdata_url(file_name)
        
        sources.append({
            "title": parent_title,
            "url": file_url,
            "chunk_text": result.get('text', '')[:200] + "...",
            "relevance_score": round(result.get('score', 0.0), 4),
            "metadata": {
                "file_name": file_name,
                "chunk_index": result.get('chunk_index', 0),
                "parent_type": result.get('parent_type', ''),
                "has_url": file_url is not None
            }
        })
    
    return sources


def _construct_lovdata_url(filename: str) -> str:
    """Fallback: Construct Lovdata URL from filename"""
    try:
        clean_name = filename.replace('.xml', '')
        parts = clean_name.split('-')
        
        if len(parts) < 2:
            return None
        
        doc_type = parts[0].upper()
        date_str = parts[1]
        
        if len(date_str) == 8:
            year = date_str[:4]
            month = date_str[4:6]
            day = date_str[6:8]
            date_formatted = f"{year}-{month}-{day}"
        else:
            return None
        
        if len(parts) >= 3:
            number = parts[2]
            url = f"https://lovdata.no/dokument/{doc_type}/{'lov' if doc_type == 'NL' else 'forskrift'}/{date_formatted}-{number}"
        else:
            url = f"https://lovdata.no/dokument/{doc_type}/{'lov' if doc_type == 'NL' else 'forskrift'}/{date_formatted}"
        
        return url
        
    except Exception as e:
        logger.warning(f"Could not construct URL from filename {filename}: {e}")
        return None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )