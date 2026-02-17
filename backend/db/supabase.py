
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class SupabaseClient:
    """
    Supabase client with all database operations
    Handles conversations, messages, metadata, and RAG retrievals
    """
    
    _instance: Optional['SupabaseClient'] = None
    _client: Optional[Client] = None
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def table(self, *args, **kwargs):
        return self.get_client().table(*args, **kwargs)

    def __init__(self):
        """Initialize Supabase client (called once due to singleton)"""
        if not hasattr(self, 'initialized'):
            self.supabase_url: Optional[str] = None
            self.initialized = False
            logger.info("Supabase client instance created")
    
    def connect(self, url: str, key: str) -> None:
        """
        Connect to Supabase
        
        Args:
            url: Supabase project URL
            key: Supabase anon/public key
            
        Raises:
            ConnectionError: If connection fails
        """
        try:
            logger.info(f"🔌 Connecting to Supabase at {url[:30]}...")
            
            self.supabase_url = url
            self._client = create_client(url, key)
            
            # Test connection by querying users table
            test_response = self._client.table("users").select("user_id").limit(1).execute()
            
            logger.info(f"✅ Connected to Supabase | URL: {url[:30]}...")
            self.initialized = True
            
        except Exception as e:
            logger.error(
                f"❌ Supabase connection failed | "
                f"URL: {url[:30]}... | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            raise ConnectionError(f"Failed to connect to Supabase: {str(e)}") from e
    
    def get_client(self) -> Client:
        """
        Get Supabase client instance
        
        Returns:
            Supabase Client
            
        Raises:
            RuntimeError: If not initialized
        """
        if not self.initialized or self._client is None:
            error_msg = "Supabase client not initialized. Call connect() first."
            logger.error(f"❌ {error_msg}")
            raise RuntimeError(error_msg)
        return self._client
    
    def check_connection(self) -> bool:
        """
        Check if Supabase connection is alive
        
        Returns:
            bool: True if connected, False otherwise
        """
        try:
            if not self.initialized or self._client is None:
                logger.warning("⚠️  Supabase not initialized")
                return False
            
            # Simple query to test connection
            self._client.table("users").select("user_id").limit(1).execute()
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Supabase health check failed | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONVERSATION OPERATIONS
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
            Created conversation data
            
        Raises:
            ValueError: If creation fails
        """
        try:
            client = self.get_client()
            conversation_id = str(uuid4())
            
            response = client.table("conversations").insert({
                "conversation_id": conversation_id,
                "user_id": user_id,
                "title": title or "New conversation",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }).execute()
            
            conversation = response.data[0]
            
            logger.info(
                f"✅ Created conversation | "
                f"ID: {conversation_id} | "
                f"User: {user_id} | "
                f"Title: {title}"
            )
            
            return conversation
            
        except Exception as e:
            logger.error(
                f"❌ Failed to create conversation | "
                f"User: {user_id} | "
                f"Title: {title} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            raise ValueError(f"Failed to create conversation: {str(e)}") from e
    
    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get conversation by ID
        
        Args:
            conversation_id: Conversation UUID
            
        Returns:
            Conversation data or None if not found
        """
        try:
            client = self.get_client()
            
            response = client.table("conversations").select("*").eq(
                "conversation_id", conversation_id
            ).eq(
                "is_deleted", False
            ).execute()
            
            if not response.data:
                logger.warning(f"⚠️  Conversation not found: {conversation_id}")
                return None
            
            conversation = response.data[0]
            logger.debug(f"✅ Retrieved conversation: {conversation_id}")
            
            return conversation
            
        except Exception as e:
            logger.error(
                f"❌ Failed to get conversation | "
                f"ID: {conversation_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return None
    
    def get_user_conversations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get all conversations for a user
        
        Args:
            user_id: User ID
            limit: Max results
            offset: Pagination offset
            
        Returns:
            List of conversations (sorted by updated_at DESC)
        """
        try:
            client = self.get_client()
            
            response = client.table("conversations").select("*").eq(
                "user_id", user_id
            ).eq(
                "is_deleted", False
            ).order(
                "updated_at", desc=True
            ).range(
                offset, offset + limit - 1
            ).execute()
            
            conversations = response.data
            
            logger.info(
                f"✅ Retrieved user conversations | "
                f"User: {user_id} | "
                f"Count: {len(conversations)}"
            )
            
            return conversations
            
        except Exception as e:
            logger.error(
                f"❌ Failed to get user conversations | "
                f"User: {user_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return []
    
    def update_conversation_title(
        self,
        conversation_id: str,
        title: str
    ) -> bool:
        """
        Update conversation title
        
        Args:
            conversation_id: Conversation UUID
            title: New title
            
        Returns:
            bool: True if successful
        """
        try:
            client = self.get_client()
            
            client.table("conversations").update({
                "title": title[:100],  # Max length
                "updated_at": datetime.utcnow().isoformat()
            }).eq(
                "conversation_id", conversation_id
            ).execute()
            
            logger.info(f"✅ Updated conversation title: {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Failed to update conversation title | "
                f"ID: {conversation_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    def delete_conversation(
        self,
        conversation_id: str,
        soft_delete: bool = True
    ) -> bool:
        """
        Delete conversation (soft or hard)
        
        Args:
            conversation_id: Conversation UUID
            soft_delete: If True, mark as deleted. If False, permanent delete.
            
        Returns:
            bool: True if successful
        """
        try:
            client = self.get_client()
            
            if soft_delete:
                client.table("conversations").update({
                    "is_deleted": True,
                    "deleted_at": datetime.utcnow().isoformat()
                }).eq(
                    "conversation_id", conversation_id
                ).execute()
                
                logger.info(f"✅ Soft deleted conversation: {conversation_id}")
            else:
                client.table("conversations").delete().eq(
                    "conversation_id", conversation_id
                ).execute()
                
                logger.info(f"✅ Hard deleted conversation: {conversation_id}")
            
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Failed to delete conversation | "
                f"ID: {conversation_id} | "
                f"Soft: {soft_delete} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MESSAGE OPERATIONS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        embedding: Optional[List[float]] = None
    ) -> str:
        """
        Save a message to database
        
        Args:
            conversation_id: Conversation UUID
            role: "user" or "assistant"
            content: Message content
            embedding: Optional embedding vector
            
        Returns:
            message_id (UUID string)
            
        Raises:
            ValueError: If save fails
        """
        try:
            client = self.get_client()
            message_id = str(uuid4())
            
            # Insert message
            client.table("messages").insert({
                "message_id": message_id,
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "embedding": embedding,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            
            # Update conversation timestamp
            client.table("conversations").update({
                "updated_at": datetime.utcnow().isoformat()
            }).eq(
                "conversation_id", conversation_id
            ).execute()
            
            logger.debug(
                f"✅ Saved message | "
                f"ID: {message_id} | "
                f"Conversation: {conversation_id} | "
                f"Role: {role}"
            )
            
            return message_id
            
        except Exception as e:
            logger.error(
                f"❌ Failed to save message | "
                f"Conversation: {conversation_id} | "
                f"Role: {role} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            raise ValueError(f"Failed to save message: {str(e)}") from e
    
    def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get all messages in a conversation
        
        Args:
            conversation_id: Conversation UUID
            limit: Max results
            offset: Pagination offset
            
        Returns:
            List of messages (sorted by created_at ASC)
        """
        try:
            client = self.get_client()
            
            response = client.table("messages").select(
                "message_id, conversation_id, role, content, created_at"
            ).eq(
                "conversation_id", conversation_id
            ).eq(
                "is_deleted", False
            ).order(
                "created_at", desc=False
            ).range(
                offset, offset + limit - 1
            ).execute()
            
            messages = response.data
            
            logger.debug(
                f"✅ Retrieved messages | "
                f"Conversation: {conversation_id} | "
                f"Count: {len(messages)}"
            )
            
            return messages
            
        except Exception as e:
            logger.error(
                f"❌ Failed to get messages | "
                f"Conversation: {conversation_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return []
    
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
        is_cached: bool = False
    ) -> bool:
        """
        Save message generation metadata
        
        Args:
            message_id: Message UUID
            model_name: Model used
            token_input: Input tokens
            token_output: Output tokens
            latency_ms: Latency in milliseconds
            is_cached: Whether response was cached
            
        Returns:
            bool: True if successful
        """
        try:
            client = self.get_client()
            
            client.table("message_metadata").insert({
                "message_id": message_id,
                "model_name": model_name,
                "token_input": token_input,
                "token_output": token_output,
                "latency_ms": latency_ms,
                "is_cached": is_cached,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            
            logger.debug(f"✅ Saved metadata for message: {message_id}")
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Failed to save message metadata | "
                f"Message: {message_id} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
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
        Save which chunks were retrieved for a message
        
        Args:
            message_id: Message UUID
            chunks: List of retrieved chunks with metadata
            
        Returns:
            bool: True if successful
        """
        try:
            client = self.get_client()
            
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
                client.table("rag_retrievals").insert(retrievals).execute()
                logger.debug(f"✅ Saved {len(retrievals)} RAG retrievals for message: {message_id}")
            
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Failed to save RAG retrievals | "
                f"Message: {message_id} | "
                f"Chunks: {len(chunks)} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False


# Global instance
supabase_client = SupabaseClient()


def get_supabase() -> SupabaseClient:
    """
    Get Supabase client instance (for dependency injection)
    
    Returns:
        SupabaseClient instance
    """
    return supabase_client