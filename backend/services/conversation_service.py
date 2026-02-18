"""
app/services/conversation_service.py
Conversation management service (CRUD operations + context building)
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from uuid import uuid4
from ..db.supabase import SupabaseClient
from ..db.redis import RedisClient
from ..models import ContextWindow, ContextMessage
from ..config import settings

logger = logging.getLogger(__name__)


class ConversationService:
    """
    Manages conversations in Supabase with Redis caching
    
    Responsibilities:
    - Create/Read/Update/Delete conversations
    - Load conversation history
    - Build context window for LLM
    - Handle conversation summaries
    """
    
    def __init__(
        self,
        supabase_client: SupabaseClient,
        redis_client: RedisClient
    ):
        self.supabase = supabase_client
        self.redis = redis_client
        self.cache = self.redis  
        logger.info("Conversation service initialized")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONVERSATION CRUD
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def create_conversation(
        self,
        user_id: str,
        title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new conversation
        
        Args:
            user_id: User ID
            title: Optional conversation title
        
        Returns:
            Conversation dict with conversation_id
        """
        try:
            # Generate new conversation ID
            conversation_id = str(uuid4())
            
            conversation = self.supabase.create_conversation(
                user_id=user_id,
                title=title
            )
            conversation_id = conversation["conversation_id"]  # Get the generated ID

            # Cache conversation metadata
            self.cache.set_conversation_meta(conversation_id, conversation)
            
            # Add to user's conversation list cache
            self.cache.add_conversation_to_user(user_id, conversation_id)
            
            logger.info(f"Created conversation: {conversation_id} for user: {user_id}")
            
            return conversation
            
        except Exception as e:
            logger.error(f"Failed to create conversation: {e}")
            raise
    
    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get conversation details
        
        Returns:
            Conversation dict or None if not found
        """
        try:
            # Try cache first
            cached = self.cache.get_conversation_meta(conversation_id)
            if cached:
                logger.debug(f"Conversation meta cache hit: {conversation_id}")
                return cached
            
            # Load from Supabase
            response = self.supabase.table("conversations").select("*").eq(
                "conversation_id", conversation_id
            ).eq(
                "is_deleted", False
            ).execute()
            
            if not response.data:
                logger.warning(f"Conversation not found: {conversation_id}")
                return None
            
            conversation = response.data[0]
            
            # Cache it
            self.cache.set_conversation_meta(conversation_id, conversation)
            
            return conversation
            
        except Exception as e:
            logger.error(f"Failed to get conversation: {e}")
            return None
    
    def get_user_conversations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get all conversations for a user
        
        Returns:
            List of conversation dicts (sorted by updated_at DESC)
        """
        try:
            # Try cache first
            cached_ids = self.cache.get_user_conversations(user_id)
            
            if cached_ids:
                logger.debug(f"User conversations cache hit: {user_id}")
                # Load each conversation (they might be individually cached)
                conversations = []
                for conv_id in cached_ids:
                    conv = self.get_conversation(conv_id)
                    if conv:
                        conversations.append(conv)
                return conversations
            
            # Load from Supabase
            response = self.supabase.table("conversations").select(
                "*"
            ).eq(
                "user_id", user_id
            ).eq(
                "is_deleted", False
            ).order(
                "updated_at", desc=True
            ).range(
                offset, offset + limit - 1
            ).execute()
            
            conversations = response.data
            
            # Cache conversation IDs
            conversation_ids = [c["conversation_id"] for c in conversations]
            self.cache.set_user_conversations(user_id, conversation_ids)
            
            # Cache individual conversations
            for conv in conversations:
                self.cache.set_conversation_meta(conv["conversation_id"], conv)
            
            logger.info(f"Loaded {len(conversations)} conversations for user: {user_id}")
            
            return conversations
            
        except Exception as e:
            logger.error(f"Failed to get user conversations: {e}")
            return []
    
    def update_conversation_title(
        self,
        conversation_id: str,
        title: str
    ) -> bool:
        """Update conversation title and refresh cache"""
        try:
            # 1. Update title in Supabase
            self.supabase.table("conversations").update({
                "title": title[:settings.MAX_CONVERSATION_TITLE_LENGTH],
                "updated_at": datetime.utcnow().isoformat()
            }).eq(
                "conversation_id", conversation_id
            ).execute()

            # 2. Clear existing cache (avoid stale data)
            self.cache.clear_all_conversation_cache(conversation_id)

            # 3. Fetch updated conversation from DB
            response = self.supabase.table("conversations").select("*").eq(
                "conversation_id", conversation_id
            ).eq(
                "is_deleted", False
            ).execute()

            if response.data:
                updated_conversation = response.data[0]

                # 4. Re-cache updated metadata
                self.cache.set_conversation_meta(
                    conversation_id,
                    updated_conversation
                )

            logger.info(f"Updated conversation title and refreshed cache: {conversation_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update conversation title: {e}")
            return False

    
    def delete_conversation(
        self,
        conversation_id: str,
        soft_delete: bool = True
    ) -> bool:

        try:
            if soft_delete:
                response = self.supabase.table("conversations").update({
                    "is_deleted": True,
                    "deleted_at": datetime.utcnow().isoformat()
                }).eq(
                    "conversation_id", conversation_id
                ).execute()
            else:
                response = self.supabase.table("conversations").delete().eq(
                    "conversation_id", conversation_id
                ).execute()

            if not response.data:
                logger.error(f"Delete failed: {conversation_id}")
                return False

            # 🔥 ALSO soft delete messages
            self.supabase.table("messages").update({
                "is_deleted": True,
                "deleted_at": datetime.utcnow().isoformat()
            }).eq(
                "conversation_id", conversation_id
            ).execute()

            self.cache.clear_all_conversation_cache(conversation_id)

            logger.info(f"Deleted conversation: {conversation_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete conversation: {e}")
            return False

    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONTEXT BUILDING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def build_context_window(
        self,
        conversation_id: str,
        max_messages: Optional[int] = None
    ) -> ContextWindow:
        """
        Build context window for LLM
        
        Strategy:
        1. Try Redis cache first (fast)
        2. If miss, load from Supabase
        3. If conversation has 50+ messages, include summary
        4. Return last N messages + optional summary
        
        Args:
            conversation_id: Conversation UUID
            max_messages: Max messages to include (default: settings.MAX_CONTEXT_MESSAGES)
        
        Returns:
            ContextWindow with messages and optional summary
        """
        try:
            if max_messages is None:
                max_messages = settings.MAX_CONTEXT_MESSAGES
            
            # Step 1: Try Redis cache
            cached_messages = self.cache.get_context(conversation_id)
            
            if cached_messages:
                logger.debug(f"Context cache hit: {conversation_id} ({len(cached_messages)} messages)")
                
                # Convert to ContextMessage objects
                context_messages = [
                    ContextMessage(
                        role=msg["role"],
                        content=msg["content"],
                        timestamp=datetime.fromisoformat(msg["timestamp"])
                    )
                    for msg in cached_messages[-max_messages:]
                ]
                
                return ContextWindow(
                    messages=context_messages,
                    summary=None,
                    total_messages=len(cached_messages)
                )
            
            # Step 2: Load from Supabase
            logger.debug(f"Context cache miss: {conversation_id}, loading from Supabase...")
            
            response = self.supabase.table("messages").select(
                "role, content, created_at"
            ).eq(
                "conversation_id", conversation_id
            ).eq(
                "is_deleted", False
            ).order(
                "created_at", desc=False
            ).execute()
            
            all_messages = response.data
            total_messages = len(all_messages)
            
            logger.debug(f"Loaded {total_messages} messages from Supabase")
            
            # Step 3: Get summary if conversation is large
            summary = None
            if total_messages > settings.AUTO_SUMMARY_THRESHOLD:
                summary = self._get_latest_summary(conversation_id)
            
            # Step 4: Take last N messages
            recent_messages = all_messages[-max_messages:]
            
            # Step 5: Cache in Redis for next time
            cache_data = [
                {
                    "role": msg["role"],
                    "content": msg["content"],
                    "timestamp": msg["created_at"]
                }
                for msg in recent_messages
            ]
            self.cache.set_context(conversation_id, cache_data)
            
            # Convert to ContextMessage objects
            context_messages = [
                ContextMessage(
                    role=msg["role"],
                    content=msg["content"],
                    timestamp=datetime.fromisoformat(msg["created_at"])
                )
                for msg in recent_messages
            ]
            
            return ContextWindow(
                messages=context_messages,
                summary=summary,
                total_messages=total_messages
            )
            
        except Exception as e:
            logger.error(f"Failed to build context window: {e}")
            # Return empty context on error
            return ContextWindow(messages=[], summary=None, total_messages=0)
    
    def _get_latest_summary(self, conversation_id: str) -> Optional[str]:
        """Get the most recent conversation summary"""
        try:
            response = self.supabase.table("conversation_summaries").select(
                "summary_text"
            ).eq(
                "conversation_id", conversation_id
            ).order(
                "created_at", desc=True
            ).limit(1).execute()
            
            if response.data:
                return response.data[0]["summary_text"]
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get summary: {e}")
            return None
    
    def format_context_for_llm(self, context: ContextWindow) -> str:
        """
        Format context window into a string for LLM
        
        Output format:
        ```
        [Summary: Previous discussion covered...]
        
        Recent messages:
        User: How does this work?
        Assistant: Let me explain...
        User: Thanks!
        ```
        """
        parts = []
        
        # Add summary if available
        if context.summary:
            parts.append(f"[Summary of previous discussion ({context.total_messages - len(context.messages)} messages): {context.summary}]\n")
        
        # Add recent messages
        if context.messages:
            parts.append("Recent conversation:")
            for msg in context.messages:
                parts.append(f"{msg.role.capitalize()}: {msg.content}")
        
        return "\n".join(parts)
    
    def get_last_n_messages_for_intent(
        self,
        conversation_id: str,
        n: int = 2
    ) -> List[Dict[str, str]]:
        """
        Get last N messages for intent detection
        
        Intent detection only needs:
        - Last user message
        - Last assistant message (for context)
        
        Returns:
            List of {"role": "user/assistant", "content": "..."}
        """
        try:
            # Try cache first
            cached = self.cache.get_context(conversation_id)
            if cached:
                return cached[-n:]
            
            # Load from Supabase
            response = self.supabase.table("messages").select(
                "role, content"
            ).eq(
                "conversation_id", conversation_id
            ).eq(
                "is_deleted", False
            ).order(
                "created_at", desc=True
            ).limit(n).execute()
            
            # Reverse to get chronological order
            messages = list(reversed(response.data))
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get messages for intent: {e}")
            return []