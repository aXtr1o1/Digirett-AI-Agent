"""
app/services/milvus_service.py
Milvus vector database service
"""

import logging
from typing import List, Dict, Any, Optional
from pymilvus import connections, Collection, utility
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings

logger = logging.getLogger(__name__)


class MilvusService:
    """Service for interacting with Milvus vector database"""
    
    def __init__(self, host: str, port: int, collection_name: str):
        """
        Initialize Milvus service
        
        Args:
            host: Milvus server host
            port: Milvus server port
            collection_name: Name of the collection to use
        """
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.collection: Optional[Collection] = None
        
        self._connect()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _connect(self):
        """Connect to Milvus with retry logic"""
        try:
            logger.info(f"Connecting to Milvus at {self.host}:{self.port}...")
            
            connections.connect(
                alias="default",
                host=self.host,
                port=self.port
            )
            
            if not utility.has_collection(self.collection_name):
                raise ValueError(f"Collection '{self.collection_name}' does not exist in Milvus")
            
            self.collection = Collection(self.collection_name)
            self.collection.load()
            
            # Get collection info
            stats = self.collection.num_entities
            logger.info(f"Connected to Milvus collection '{self.collection_name}' with {stats} entities")
            
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise
    
    def check_connection(self) -> bool:
        """Check if connection is alive"""
        try:
            if self.collection is None:
                return False
            
            _ = self.collection.num_entities
            return True
            
        except Exception as e:
            logger.error(f"Milvus connection check failed: {e}")
            return False
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def search(
        self,
        embedding: List[float],
        top_k: int = 3,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors in Milvus
        
        Args:
            embedding: Query embedding vector
            top_k: Number of results to return
            min_score: Minimum similarity score
            
        Returns:
            List of search results with metadata
        """
        try:
            logger.info(f"Searching Milvus for top-{top_k} results...")
            
            if self.collection is None:
                raise RuntimeError("Milvus collection not initialized")
            
            # Define search parameters
            search_params = {
                "metric_type": settings.MILVUS_METRIC_TYPE,
                "params": {"ef": 64}
            }
            
            # Output fields to retrieve - ADDED file_url / lovdata_url
            output_fields = [
                "chunk_id",
                "file_name",
                "text",
                "parent_title",
                "parent_type",
                "chunk_index",
                "parent_index",
                "child_index",
                "url",      # NEW: URL field   # NEW: Alternative URL field name
            ]
            
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
                    score = hit.distance
                    
                    if score < min_score:
                        continue
                    
                    entity = hit.entity
                    
                    result_dict = {
                        "score": float(score)
                    }
                    
                    # Extract fields safely
                    try:
                        result_dict["chunk_id"] = getattr(entity, "chunk_id", "")
                        result_dict["file_name"] = getattr(entity, "file_name", "")
                        result_dict["text"] = getattr(entity, "text", "")
                        result_dict["parent_title"] = getattr(entity, "parent_title", "")
                        result_dict["parent_type"] = getattr(entity, "parent_type", "")
                        result_dict["chunk_index"] = getattr(entity, "chunk_index", 0)
                        result_dict["parent_index"] = getattr(entity, "parent_index", 0)
                        result_dict["child_index"] = getattr(entity, "child_index", 0)
                        
                        # NEW: Get URL from metadata (try both field names)
                        file_url = getattr(entity, "url", None)
                        result_dict["file_url"] = file_url or None
                        
                    except AttributeError:
                        # Fallback to dictionary access
                        try:
                            result_dict["chunk_id"] = entity.get("chunk_id", "")
                            result_dict["file_name"] = entity.get("file_name", "")
                            result_dict["text"] = entity.get("text", "")
                            result_dict["parent_title"] = entity.get("parent_title", "")
                            result_dict["parent_type"] = entity.get("parent_type", "")
                            result_dict["chunk_index"] = entity.get("chunk_index", 0)
                            result_dict["parent_index"] = entity.get("parent_index", 0)
                            result_dict["child_index"] = entity.get("child_index", 0)
                            
                            # NEW: Get URL
                            file_url = entity.get("url")
                            result_dict["file_url"] = file_url or None
                        except:
                            logger.warning(f"Could not extract full entity data from hit")
                            result_dict.update({
                                "chunk_id": "",
                                "file_name": "",
                                "text": str(entity) if entity else "",
                                "parent_title": "",
                                "parent_type": "",
                                "chunk_index": 0,
                                "parent_index": 0,
                                "child_index": 0,
                                "file_url": None
                            })
                    
                    processed_results.append(result_dict)
            
            logger.info(f"Found {len(processed_results)} results")
            return processed_results
            
        except Exception as e:
            logger.error(f"Milvus search failed: {e}", exc_info=True)
            raise
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics"""
        try:
            if self.collection is None:
                return {"error": "Collection not initialized"}
            
            return {
                "name": self.collection_name,
                "num_entities": self.collection.num_entities,
                "schema": str(self.collection.schema)
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"error": str(e)}
    
    def close(self):
        """Close Milvus connection"""
        try:
            if self.collection:
                self.collection.release()
            connections.disconnect("default")
            logger.info("Milvus connection closed")
            
        except Exception as e:
            logger.error(f"Error closing Milvus connection: {e}")