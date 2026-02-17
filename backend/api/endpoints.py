import logging
import json
from typing import Optional
from uuid import uuid4
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from . . models import (
    ChatRequest,
    ConversationCreate,
    ConversationResponse,
    ConversationHistoryResponse,
    MessageResponse,
    HealthResponse
)
from ..services.rag_service import RAGService
from ..services.llm_service import LLMService
from ..services.conversation_service import ConversationService
from ..services.message_service import MessageService
from ..db.milvus_client import MilvusClient
from ..db.redis import RedisClient
from ..db.supabase import SupabaseClient

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

# Create routers
router = APIRouter()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DEPENDENCY INJECTION (set by main.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

rag_service: Optional[RAGService] = None
conversation_service: Optional[ConversationService] = None
message_service: Optional[MessageService] = None
milvus_client: Optional[MilvusClient] = None
redis_client: Optional[RedisClient] = None
supabase_client: Optional[SupabaseClient] = None
llm_services: Optional[LLMService] = None



def set_services(
    rag: RAGService,
    conv: ConversationService,
    msg: MessageService,
    milvus: MilvusClient,
    redis: RedisClient,
    llm: LLMService,
    supabase: SupabaseClient
):
    """Set service instances (called from main.py)"""
    global rag_service, conversation_service, message_service, llm_services
    global milvus_client, redis_client, supabase_client
    
    rag_service = rag
    conversation_service = conv
    message_service = msg
    milvus_client = milvus
    redis_client = redis
    supabase_client = supabase
    llm_services = llm
    
    logger.info("✅ Services injected into endpoints")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HEALTH CHECK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Check system health"""
    try:
        milvus_status = milvus_client.check_connection() if milvus_client else False
        redis_status = redis_client.check_connection() if redis_client else False
        supabase_status = supabase_client.check_connection() if supabase_client else False
        llm_status = await llm_services.check_connection() if llm_services else False 
        
        
        all_healthy = all([milvus_status, redis_status, supabase_status, llm_status])
        
        return HealthResponse(
            status="healthy" if all_healthy else "degraded",
            version="2.0.0",
            milvus_connected=milvus_status,
            cache_connected=redis_status,
            llm_connected=llm_status,  
            supabase_connected=supabase_status
        )
        
    except Exception as e:
        logger.error(
            f"❌ Health check failed | "
            f"Error: {type(e).__name__}: {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unhealthy: {str(e)}"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONVERSATION MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/conversations", response_model=ConversationResponse, tags=["Conversations"])
@limiter.limit("100/minute")
async def create_conversation(request: Request, conversation_request: ConversationCreate):
    """Create a new conversation"""
    try:
        conversation = conversation_service.create_conversation(
            user_id=conversation_request.user_id,
            title=conversation_request.title
        )
        
        return ConversationResponse(**conversation)
        
    except Exception as e:
        logger.error(
            f"❌ Failed to create conversation | "
            f"User: {conversation_request.user_id} | "
            f"Error: {type(e).__name__}: {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create conversation: {str(e)}"
        )


@router.get("/conversations/{conversation_id}", response_model=ConversationHistoryResponse, tags=["Conversations"])
@limiter.limit("100/minute")
async def get_conversation(request: Request, conversation_id: str):
    """Get conversation details with messages"""
    try:
        # Get conversation
        conversation = conversation_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        # Get messages
        messages = message_service.get_conversation_messages(conversation_id)
        
        return ConversationHistoryResponse(
            conversation=ConversationResponse(**conversation),
            messages=[MessageResponse(**msg) for msg in messages],
            summary=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"❌ Failed to get conversation | "
            f"ID: {conversation_id} | "
            f"Error: {type(e).__name__}: {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get conversation: {str(e)}"
        )


@router.get("/conversations/user/{user_id}", response_model=list[ConversationResponse], tags=["Conversations"])
@limiter.limit("100/minute")
async def get_user_conversations(request: Request, user_id: str, limit: int = 50, offset: int = 0):
    """Get all conversations for a user"""
    try:
        conversations = conversation_service.get_user_conversations(
            user_id=user_id,
            limit=limit,
            offset=offset
        )
        
        return [ConversationResponse(**conv) for conv in conversations]
        
    except Exception as e:
        logger.error(
            f"❌ Failed to get user conversations | "
            f"User: {user_id} | "
            f"Error: {type(e).__name__}: {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user conversations: {str(e)}"
        )


@router.delete("/conversations/{conversation_id}", tags=["Conversations"])
@limiter.limit("100/minute")
async def delete_conversation(request: Request, conversation_id: str):
    """Delete a conversation (soft delete)"""
    try:
        success = conversation_service.delete_conversation(
            conversation_id=conversation_id,
            soft_delete=True
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete conversation"
            )
        
        return {"status": "deleted", "conversation_id": conversation_id}
        
    except Exception as e:
        logger.error(
            f"❌ Failed to delete conversation | "
            f"ID: {conversation_id} | "
            f"Error: {type(e).__name__}: {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete conversation: {str(e)}"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MESSAGES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/messages/{conversation_id}", response_model=list[MessageResponse], tags=["Messages"])
@limiter.limit("100/minute")
async def get_messages(request: Request, conversation_id: str):
    """Fetch messages for a conversation"""
    try:
        messages = message_service.get_conversation_messages(conversation_id)
        return [MessageResponse(**msg) for msg in messages]
        
    except Exception as e:
        logger.error(
            f"❌ Failed to fetch messages | "
            f"Conversation: {conversation_id} | "
            f"Error: {type(e).__name__}: {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch messages"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHAT STREAMING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/chat/stream", tags=["RAG"])
@limiter.limit("250/minute")
async def chat_stream(request: Request, chat_request: ChatRequest):
    """
    Stream answer with conversation context
    
    Flow:
    1. Get/create conversation
    2. Process query with RAG service (agent routing)
    3. Stream response
    4. Save messages to Supabase
    5. Update Redis cache
    """
    
    async def generate_stream():
        start_time = datetime.utcnow()
        conversation_id = None
        user_msg_id = None
        assistant_msg_id = None
        full_answer = ""
        intent = "UNKNOWN"
        language = "english"
        rag_chunks = []
        
        try:
            logger.info(f"💬 Streaming chat request: '{chat_request.query[:100]}...'")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 1: Get or create conversation
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            conversation_id = chat_request.conversation_id
            user_id = chat_request.user_id

            # If no conversation_id → create one first
            if not conversation_id:
                conversation = conversation_service.create_conversation(
                    user_id=user_id,
                    title=chat_request.query[:50]
                )
                conversation_id = conversation["conversation_id"]
                logger.info(f"✅ Auto-created conversation: {conversation_id}")

            # Now load conversation history
            conversation_history = message_service.get_llm_context(
                conversation_id=conversation_id,
                limit=10
            )

            logger.info(
                "🧠 Loaded %d messages for LLM context (conversation_id=%s)",
                len(conversation_history),
                conversation_id
            )

            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 2: Process query with RAG service (agent routing)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            async for event in rag_service.process_query(
                query=chat_request.query,
                conversation_id=conversation_id,
                top_k=chat_request.top_k
            ):
                event_type = event.get("type")
                
                # Track intent
                if event_type == "intent":
                    intent = event["data"]["intent"]
                    language = event["data"]["language"]
                    logger.info(f"🎯 Intent: {intent}, Language: {language}")
                
                # Stream tokens
                elif event_type == "token":
                    full_answer += event["data"]
                    yield f"data: {json.dumps(event)}\n\n"
                
                # Stream sources
                elif event_type == "sources":
                    rag_chunks = event.get("data", [])
                    print("🟡 SOURCES EVENT RECEIVED:", rag_chunks)   # ✅ ADD HERE
                    yield f"data: {json.dumps(event)}\n\n"

                
                # Completion
                elif event_type == "complete":
                    metadata = event["metadata"]
                    full_answer = metadata.get("full_answer", full_answer)
                    rag_chunks = metadata.get("rag_chunks") or rag_chunks   
                    print("🔵 FINAL rag_chunks BEFORE SAVE:", rag_chunks)  # ✅ ADD HERE                 
                    print("COMPLETE METADATA:", metadata)
                    print("RAG CHUNKS AT SAVE:", rag_chunks)


                    try:
                        query_time = (datetime.utcnow() - start_time).total_seconds()

                        user_msg_id, assistant_msg_id = message_service.save_user_and_assistant_messages(
                            conversation_id=conversation_id,
                            user_message=chat_request.query,
                            assistant_message=full_answer,
                            metadata={
                                "intent": intent,
                                "language": language,
                                "tokens_used": metadata.get("tokens_generated", 0),
                                "query_time": query_time,
                                "model": "gpt-4.1-mini",
                                "score": metadata.get("score", 1.0),
                                "confidence": metadata.get("confidence", "Unknown"),
                                "chunks_retrieved": metadata.get("chunks_retrieved", 0)
                            },
                            rag_chunks=rag_chunks
                        )

                        logger.info(f"✅ Saved messages: user={user_msg_id}, assistant={assistant_msg_id}")

                        # 🔥 NORMALIZE SOURCES FOR STREAM RESPONSE
                        normalized_sources = []
                        for chunk in rag_chunks:
                            if isinstance(chunk, dict):
                                url = chunk.get("url")
                                if not url and chunk.get("chunk_id"):
                                    url = f"https://lovdata.no/dokument/{chunk.get('chunk_id')}"

                                if url:
                                    normalized_sources.append({
                                        "title": chunk.get("file_name") or chunk.get("chunk_id") or "Source",
                                        "url": url
                                    })

                    except Exception as save_error:
                        logger.error(
                            f"❌ Failed to save messages | "
                            f"Conversation: {conversation_id} | "
                            f"Error: {type(save_error).__name__}: {str(save_error)}",
                            exc_info=True
                        )

                    # 🔥 Attach everything properly
                    metadata["conversation_id"] = conversation_id
                    metadata["message_id"] = assistant_msg_id
                    metadata["sources"] = normalized_sources  # ✅ THIS WAS MISSING

                    yield f"data: {json.dumps({'type': 'complete', 'metadata': metadata})}\n\n"
                
                # Error
                elif event_type == "error":
                    yield f"data: {json.dumps(event)}\n\n"
            
        except Exception as e:
            logger.error(
                f"❌ Streaming error | "
                f"Query: {chat_request.query[:50]} | "
                f"Conversation: {conversation_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )