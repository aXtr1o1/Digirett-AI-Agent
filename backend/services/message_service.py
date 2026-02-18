"""
app/services/message_service.py
Message management service (CRUD operations + metadata tracking)
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4
from supabase import Client

from ..db.supabase import SupabaseClient
from ..db.redis import RedisClient
from ..config import settings

logger = logging.getLogger(__name__)


class MessageService:
    """
    Manages messages in Supabase with Redis caching
    
    Responsibilities:
    - Save user/assistant messages
    - Track message metadata (tokens, latency, model info)
    - Track RAG retrievals per message
    - Update conversation updated_at timestamp
    """
    
    def __init__(
        self,
        supabase_client: SupabaseClient,
        redis_client: RedisClient
    ):
        self.supabase = supabase_client
        self.redis = redis_client
        self.cache = self.redis
        logger.info("Message service initialized")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MESSAGE CRUD
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Save a message to Supabase
        
        Args:
            conversation_id: Conversation UUID
            role: "user" or "assistant"
            content: Message text
            embedding: Optional embedding vector for semantic search
        
        Returns:
            message_id (UUID string)
        """
        try:
            message_id = str(uuid4())
            
            # Insert message
            self.supabase.table("messages").insert({
                "message_id": message_id,
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "embedding": embedding,
                "sources": sources if role == "assistant" else None,
                "metadata": metadata,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            print("SAVING SOURCES:", sources)

            # Update conversation's updated_at
            self.supabase.table("conversations").update({
                "updated_at": datetime.utcnow().isoformat()
            }).eq(
                "conversation_id", conversation_id
            ).execute()
            
            # Update Redis cache
            self.cache.append_message_to_context(
                conversation_id=conversation_id,
                role=role,
                content=content,
                timestamp=datetime.utcnow()
            )
            
            # Extend context TTL (sliding window)
            self.cache.extend_context_ttl(conversation_id)
            
            logger.debug(f"Saved {role} message: {message_id} in conversation: {conversation_id}")
            
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to save message: {e}")
            raise
    def get_llm_context(
        self,
        conversation_id: str,
        limit: int = 10
    ) -> List[Dict[str, str]]:
        messages = self.get_conversation_messages(
            conversation_id=conversation_id,
            limit=limit
        )

        llm_messages = []
        for msg in messages:
            if msg["role"] in ("user", "assistant"):
                llm_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # ✅ ADD DEBUG LOGGING
        logger.info(
            f"📚 Loaded LLM context | "
            f"Conversation: {conversation_id} | "
            f"Messages: {len(llm_messages)} | "
            f"Content preview: {llm_messages[:2] if llm_messages else 'empty'}"
        )

        return llm_messages

    def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:

        try:
            response = self.supabase.table("messages").select(
                "message_id, conversation_id, role, content, sources, metadata, created_at"
            ).eq(
                "conversation_id", conversation_id
            ).or_(
                "is_deleted.is.null,is_deleted.eq.false"
            ).order(
                "created_at", desc=False
            ).range(
                offset, offset + limit - 1
            ).execute()

            messages = response.data or []

            for msg in messages:
                if msg["role"] == "assistant":
                    raw_sources = msg.get("sources") or []
                    normalized_sources = []

                    for chunk in raw_sources:
                        if isinstance(chunk, dict):
                            url = chunk.get("url")

                            # Safety fallback if old messages missing url
                            if not url and chunk.get("chunk_id"):
                                url = f"https://lovdata.no/dokument/{chunk.get('chunk_id')}"

                            if url:
                                normalized_sources.append({
                                    "title": chunk.get("title") or chunk.get("file_name") or chunk.get("chunk_id") or "Source",
                                    "url": url
                                })

                    msg["sources"] = normalized_sources
                else:
                    msg["sources"] = []


            return messages

        except Exception as e:
            logger.error(f"Failed to get conversation messages: {e}")
            return []


    
    def delete_message(
        self,
        message_id: str,
        soft_delete: bool = True
    ) -> bool:
        """Delete a message (soft or hard)"""
        try:
            if soft_delete:
                self.supabase.table("messages").update({
                    "is_deleted": True,
                    "deleted_at": datetime.utcnow().isoformat()
                }).eq(
                    "message_id", message_id
                ).execute()
                
                logger.info(f"Soft deleted message: {message_id}")
            else:
                self.supabase.table("messages").delete().eq(
                    "message_id", message_id
                ).execute()
                
                logger.info(f"Hard deleted message: {message_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete message: {e}")
            return False
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MESSAGE METADATA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def save_message_metadata(
        self,
        message_id: str,
        model_name: str,
        token_input: int,
        token_output: int,
        latency_ms: int,
        is_cached: bool = False,
        model_version: Optional[str] = None,
        prompt_version: Optional[str] = None
    ) -> bool:
        """
        Save metadata about message generation
        
        Tracks:
        - Model used
        - Token usage
        - Latency
        - Cache hits
        """
        try:
            self.supabase.table("message_metadata").insert({
                "message_id": message_id,
                "model_name": model_name,
                "model_version": model_version,
                "prompt_version": prompt_version,
                "token_input": token_input,
                "token_output": token_output,
                "latency_ms": latency_ms,
                "is_cached": is_cached,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            
            logger.debug(f"Saved metadata for message: {message_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save message metadata: {e}")
            return False
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RAG RETRIEVAL TRACKING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def save_rag_retrievals(
        self,
        message_id: str,
        chunks: List[Dict[str, Any]]
    ) -> bool:
        """
        Save which chunks were retrieved for this message
        
        Args:
            message_id: Message UUID
            chunks: List of retrieved chunks from Milvus with metadata
        
        Example chunks format:
        [
            {
                "chunk_id": "chunk_123",
                "similarity_score": 0.92,
                "rank": 1
            }
        ]
        """
        try:
            # Prepare batch insert
            retrievals = []
            for idx, chunk in enumerate(chunks, start=1):
                retrievals.append({
                    "message_id": message_id,
                    "chunk_id": chunk.get("chunk_id", chunk.get("file_name", "unknown")),
                    "similarity_score": chunk.get("score", 0.0),
                    "rank": idx,
                    "created_at": datetime.utcnow().isoformat()
                })
            
            if retrievals:
                self.supabase.table("rag_retrievals").insert(retrievals).execute()
                logger.debug(f"Saved {len(retrievals)} RAG retrievals for message: {message_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save RAG retrievals: {e}")
            return False
    
    def get_message_retrievals(self, message_id: str) -> List[Dict[str, Any]]:
        """Get which chunks were used for a message"""
        try:
            response = self.supabase.table("rag_retrievals").select(
                "*"
            ).eq(
                "message_id", message_id
            ).order(
                "rank", desc=False
            ).execute()
            
            return response.data
            
        except Exception as e:
            logger.error(f"Failed to get message retrievals: {e}")
            return []
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BULK OPERATIONS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def save_user_and_assistant_messages(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        metadata: Dict[str, Any],
        rag_chunks: Optional[List[Dict[str, Any]]] = None
    ) -> tuple[str, str]:
        """
        Save both user and assistant messages in one transaction
        
        This is the main method called after generating a response
        
        Args:
            conversation_id: Conversation UUID
            user_message: User's query
            assistant_message: AI's response
            metadata: Generation metadata (tokens, latency, model, etc.)
            rag_chunks: Optional list of retrieved chunks
        
        Returns:
            (user_message_id, assistant_message_id)
        """
        print("🟣 rag_chunks INSIDE SAVE:", rag_chunks)
        try:
            # Save user message
            user_msg_id = self.save_message(
                conversation_id=conversation_id,
                role="user",
                content=user_message
            )
            


            normalized_sources = [
                {
                    "title": chunk.get("file_name"),
                    "url": chunk.get("url"),
                    "score": chunk.get("score"),
                }
                for chunk in rag_chunks
            ]


            # Save assistant message
            assistant_msg_id = self.save_message(
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_message,
                sources=normalized_sources,
                metadata=metadata  # 🔥 ADD THIS
            )


            
            # Save metadata for assistant message
            self.save_message_metadata(
                message_id=assistant_msg_id,
                model_name=metadata.get("model", settings.AZURE_OPENAI_DEPLOYMENT),
                token_input=metadata.get("token_input", 0),
                token_output=metadata.get("tokens_used", 0),
                latency_ms=int(metadata.get("query_time", 0) * 1000),
                is_cached=metadata.get("cached", False)
            )
            
            # Save RAG retrievals if used
            if rag_chunks:
                self.save_rag_retrievals(assistant_msg_id, rag_chunks)
            
            logger.info(
                f"Saved conversation pair: user={user_msg_id}, assistant={assistant_msg_id}"
            )
            
            return user_msg_id, assistant_msg_id
            
        except Exception as e:
            logger.error(f"Failed to save message pair: {e}")
            raise