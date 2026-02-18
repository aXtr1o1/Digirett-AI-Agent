
import logging
from typing import List, Dict, Any, Optional
from pymilvus import connections, Collection, utility
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class MilvusClient:
    """
    Milvus vector database client with all operations
    Handles connection and search operations
    """
    
    _instance: Optional['MilvusClient'] = None
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize Milvus client (called once due to singleton)"""
        if not hasattr(self, 'initialized'):
            self.host: Optional[str] = None
            self.port: Optional[int] = None
            self.collection_name: Optional[str] = None
            self.collection: Optional[Collection] = None
            self.initialized = False
            logger.info("Milvus client instance created")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def connect(self, host: str, port: int, collection_name: str) -> None:
        """
        Connect to Milvus server and load collection
        
        Args:
            host: Milvus server host
            port: Milvus server port
            collection_name: Collection name to use
            
        Raises:
            ConnectionError: If connection fails
            ValueError: If collection doesn't exist
        """
        try:
            logger.info(f"🔌 Connecting to Milvus at {host}:{port}...")
            
            self.host = host
            self.port = port
            self.collection_name = collection_name
            
            # Connect to Milvus
            connections.connect(
                alias="default",
                host=host,
                port=port
            )
            
            # Check if collection exists
            if not utility.has_collection(collection_name):
                error_msg = f"Collection '{collection_name}' does not exist in Milvus"
                logger.error(f"❌ {error_msg}")
                raise ValueError(error_msg)
            
            # Load collection
            self.collection = Collection(collection_name)
            self.collection.load()
            
            # Get stats
            num_entities = self.collection.num_entities
            logger.info(
                f"✅ Connected to Milvus collection '{collection_name}' | "
                f"Entities: {num_entities:,}"
            )
            
            self.initialized = True
            
        except Exception as e:
            logger.error(
                f"❌ Milvus connection failed | "
                f"Host: {host}:{port} | "
                f"Collection: {collection_name} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            raise ConnectionError(f"Failed to connect to Milvus: {str(e)}") from e
    
    def check_connection(self) -> bool:
        """
        Check if Milvus connection is alive
        
        Returns:
            bool: True if connected, False otherwise
        """
        try:
            if not self.initialized or self.collection is None:
                logger.warning("⚠️  Milvus not initialized")
                return False
            
            # Try to get entity count
            _ = self.collection.num_entities
            return True
            
        except Exception as e:
            logger.error(
                f"❌ Milvus health check failed | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return False
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def search(
        self,
        embedding: List[float],
        top_k: int = 3,
        min_score: float = 0.0,
        metric_type: str = "IP",
        output_fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors in Milvus
        
        Args:
            embedding: Query embedding vector (must match collection dimension)
            top_k: Number of results to return
            min_score: Minimum similarity score threshold
            metric_type: Distance metric ("IP", "L2", "COSINE")
            output_fields: Fields to retrieve (None = all available)
            
        Returns:
            List of search results with metadata
            
        Raises:
            RuntimeError: If collection not initialized
            ValueError: If search fails
        """
        try:
            if not self.initialized or self.collection is None:
                error_msg = "Milvus collection not initialized. Call connect() first."
                logger.error(f"❌ {error_msg}")
                raise RuntimeError(error_msg)
            
            logger.info(
                f"🔍 Searching Milvus | "
                f"Collection: {self.collection_name} | "
                f"Top-K: {top_k} | "
                f"Min Score: {min_score}"
            )
            
            # Default output fields
            if output_fields is None:
                output_fields = [
                    "chunk_id",
                    "file_name",
                    "text",
                    "parent_title",
                    "parent_type",
                    "chunk_index",
                    "parent_index",
                    "child_index",
                    "url",
                ]
            
            # Search parameters
            search_params = {
                "metric_type": metric_type,
                "params": {"ef": 64}  # HNSW search param
            }
            
            # Perform search
            results = self.collection.search(
                data=[embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=output_fields
            )
            
            # Process results
            processed_results = []
            for hits in results:
                for hit in hits:
                    score = float(hit.distance)
                    
                    # Filter by minimum score
                    if score < min_score:
                        logger.debug(f"Skipping result with score {score:.4f} < {min_score}")
                        continue
                    
                    entity = hit.entity
                    
                    # Extract entity data safely
                    result_dict = {"score": score}
                    
                    for field in output_fields:
                        try:
                            value = getattr(entity, field, None)
                            if value is None:
                                value = entity.get(field) if hasattr(entity, 'get') else None
                            result_dict[field] = value
                        except (AttributeError, KeyError) as e:
                            logger.debug(f"Field '{field}' not found in entity: {e}")
                            result_dict[field] = None
                    
                    processed_results.append(result_dict)
            
            logger.info(
                f"✅ Milvus search complete | "
                f"Results: {len(processed_results)}/{top_k} | "
                f"Filtered by score >= {min_score}"
            )
            
            return processed_results
            
        except Exception as e:
            logger.error(
                f"❌ Milvus search failed | "
                f"Collection: {self.collection_name} | "
                f"Top-K: {top_k} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            raise ValueError(f"Milvus search failed: {str(e)}") from e
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get collection statistics
        
        Returns:
            Dictionary with collection stats
        """
        try:
            if not self.initialized or self.collection is None:
                return {
                    "status": "not_initialized",
                    "error": "Collection not initialized"
                }
            
            stats = {
                "status": "connected",
                "collection_name": self.collection_name,
                "num_entities": self.collection.num_entities,
                "host": self.host,
                "port": self.port
            }
            
            logger.info(f"📊 Milvus stats: {stats}")
            return stats
            
        except Exception as e:
            logger.error(
                f"❌ Failed to get Milvus stats | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return {
                "status": "error",
                "error": str(e)
            }
    
    def close(self) -> None:
        """
        Close Milvus connection and release resources
        """
        try:
            if self.collection:
                self.collection.release()
                logger.info(f"📤 Released collection: {self.collection_name}")
            
            connections.disconnect("default")
            logger.info("🔌 Disconnected from Milvus")
            
            self.initialized = False
            self.collection = None
            
        except Exception as e:
            logger.error(
                f"❌ Error closing Milvus connection | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True
            )


# Global instance
milvus_client = MilvusClient()


def get_milvus() -> MilvusClient:
    """
    Get Milvus client instance (for dependency injection)
    
    Returns:
        MilvusClient instance
    """
    return milvus_client