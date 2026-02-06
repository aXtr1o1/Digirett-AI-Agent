"""
app/services/milvus_service.py - IMPROVED WITH COMPREHENSIVE LOGGING
Milvus vector database service with detailed error tracking
"""

import logging
from typing import List, Dict, Any, Optional
from pymilvus import connections, Collection, utility
from tenacity import retry, stop_after_attempt, wait_exponential
import traceback
from datetime import datetime

from ..config import settings

logger = logging.getLogger(__name__)


class MilvusService:
    """Service for interacting with Milvus vector database with comprehensive logging"""
    
    def __init__(self, host: str, port: int, collection_name: str):
        """
        Initialize Milvus service with detailed logging
        
        Args:
            host: Milvus server host
            port: Milvus server port
            collection_name: Name of the collection to use
        """
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.collection: Optional[Collection] = None
        
        init_id = f"milvus_init_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        logger.info(
            f"[{init_id}] Initializing Milvus service",
            extra={
                'context': {
                    'host': host,
                    'port': port,
                    'collection_name': collection_name,
                    'timestamp': datetime.utcnow().isoformat()
                }
            }
        )
        
        try:
            self._connect(init_id)
            logger.info(
                f"[{init_id}] ✓ Milvus service initialized successfully",
                extra={
                    'context': {
                        'collection_name': collection_name,
                        'entity_count': self.collection.num_entities if self.collection else 0
                    }
                }
            )
        except Exception as e:
            logger.error(
                f"[{init_id}] ✗ Milvus initialization FAILED",
                extra={
                    'error_details': {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': traceback.format_exc(),
                        'host': host,
                        'port': port,
                        'collection_name': collection_name
                    }
                },
                exc_info=True
            )
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _connect(self, init_id: str = None):
        """Connect to Milvus with retry logic and detailed logging"""
        if not init_id:
            init_id = f"milvus_connect_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        logger.info(
            f"[{init_id}] Attempting Milvus connection",
            extra={
                'context': {
                    'host': self.host,
                    'port': self.port,
                    'collection_name': self.collection_name
                }
            }
        )
        
        try:
            # Step 1: Connect to Milvus
            connection_start = datetime.utcnow()
            
            connections.connect(
                alias="default",
                host=self.host,
                port=self.port
            )
            
            connection_duration = (datetime.utcnow() - connection_start).total_seconds()
            
            logger.debug(
                f"[{init_id}] Connected to Milvus server",
                extra={
                    'context': {
                        'connection_duration_seconds': connection_duration,
                        'host': self.host,
                        'port': self.port
                    }
                }
            )
            
            # Step 2: Check if collection exists
            if not utility.has_collection(self.collection_name):
                error_msg = f"Collection '{self.collection_name}' does not exist in Milvus"
                logger.error(
                    f"[{init_id}] ✗ Collection not found",
                    extra={
                        'error_details': {
                            'error_type': 'CollectionNotFoundError',
                            'collection_name': self.collection_name,
                            'available_collections': utility.list_collections() if hasattr(utility, 'list_collections') else 'unknown'
                        }
                    }
                )
                raise ValueError(error_msg)
            
            logger.debug(
                f"[{init_id}] Collection exists: {self.collection_name}",
                extra={'context': {'collection_name': self.collection_name}}
            )
            
            # Step 3: Load collection
            load_start = datetime.utcnow()
            
            self.collection = Collection(self.collection_name)
            self.collection.load()
            
            load_duration = (datetime.utcnow() - load_start).total_seconds()
            
            # Step 4: Get collection stats
            stats = self.collection.num_entities
            
            logger.info(
                f"[{init_id}] ✓ Milvus connection successful",
                extra={
                    'context': {
                        'collection_name': self.collection_name,
                        'entity_count': stats,
                        'connection_duration_seconds': connection_duration,
                        'load_duration_seconds': load_duration,
                        'total_duration_seconds': connection_duration + load_duration
                    }
                }
            )
            
        except ValueError as e:
            # Collection not found - don't retry
            logger.error(
                f"[{init_id}] ✗ Milvus collection not found",
                extra={
                    'error_details': {
                        'error_type': 'ValueError',
                        'error_message': str(e),
                        'collection_name': self.collection_name,
                        'recovery_action': 'Ensure collection is created before starting the service'
                    }
                },
                exc_info=True
            )
            raise
            
        except Exception as e:
            logger.error(
                f"[{init_id}] ✗ Milvus connection failed",
                extra={
                    'error_details': {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': traceback.format_exc(),
                        'host': self.host,
                        'port': self.port,
                        'collection_name': self.collection_name,
                        'recovery_action': 'Will retry with exponential backoff'
                    }
                },
                exc_info=True
            )
            raise
    
    def check_connection(self, correlation_id: str = None) -> bool:
        """Check if connection is alive with detailed logging"""
        if not correlation_id:
            correlation_id = f"health_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        logger.debug(
            f"[{correlation_id}] Checking Milvus connection",
            extra={'context': {'collection_name': self.collection_name}}
        )
        
        try:
            if self.collection is None:
                logger.warning(
                    f"[{correlation_id}] ⚠ Milvus collection is None",
                    extra={'context': {'collection_name': self.collection_name}}
                )
                return False
            
            # Try to get entity count (lightweight operation)
            start_time = datetime.utcnow()
            entity_count = self.collection.num_entities
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            logger.debug(
                f"[{correlation_id}] ✓ Milvus connection healthy",
                extra={
                    'context': {
                        'collection_name': self.collection_name,
                        'entity_count': entity_count,
                        'check_duration_seconds': duration
                    }
                }
            )
            return True
            
        except Exception as e:
            logger.error(
                f"[{correlation_id}] ✗ Milvus connection check failed",
                extra={
                    'error_details': {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'collection_name': self.collection_name
                    }
                },
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
        correlation_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors in Milvus with comprehensive logging
        
        Args:
            embedding: Query embedding vector
            top_k: Number of results to return
            min_score: Minimum similarity score
            correlation_id: Request tracking ID
            
        Returns:
            List of search results with metadata
        """
        if not correlation_id:
            correlation_id = f"search_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        
        logger.info(
            f"[{correlation_id}] Starting Milvus search",
            extra={
                'context': {
                    'embedding_dimension': len(embedding),
                    'top_k': top_k,
                    'min_score': min_score,
                    'collection_name': self.collection_name
                }
            }
        )
        
        try:
            if self.collection is None:
                error_msg = "Milvus collection not initialized"
                logger.error(
                    f"[{correlation_id}] ✗ {error_msg}",
                    extra={
                        'error_details': {
                            'error_type': 'RuntimeError',
                            'error_message': error_msg,
                            'collection_name': self.collection_name,
                            'recovery_action': 'Reconnect to Milvus'
                        }
                    }
                )
                raise RuntimeError(error_msg)
            
            # Check and ensure collection is loaded
            load_state = utility.load_state(self.collection.name)
            logger.debug(
                f"[{correlation_id}] Collection load state: {load_state}",
                extra={'context': {'load_state': str(load_state)}}
            )
            
            if str(load_state) != "LoadState.Loaded":
                logger.info(
                    f"[{correlation_id}] Loading collection: {self.collection.name}",
                    extra={'context': {'collection_name': self.collection.name}}
                )
                self.collection.load()
            
            # Define search parameters
            search_params = {
                "metric_type": settings.MILVUS_METRIC_TYPE,
                "params": {"ef": 64}
            }
            
            # Output fields to retrieve
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
            
            logger.debug(
                f"[{correlation_id}] Executing Milvus search",
                extra={
                    'context': {
                        'search_params': search_params,
                        'output_fields_count': len(output_fields),
                        'metric_type': search_params['metric_type']
                    }
                }
            )
            
            # Perform search
            search_start = datetime.utcnow()
            
            results = self.collection.search(
                data=[embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=output_fields
            )
            
            search_duration = (datetime.utcnow() - search_start).total_seconds()
            
            # Process results
            processed_results = []
            score_distribution = {"min": float('inf'), "max": 0.0, "avg": 0.0}
            
            for hits in results:
                for hit in hits:
                    score = hit.distance
                    
                    # Track score distribution
                    score_distribution["min"] = min(score_distribution["min"], score)
                    score_distribution["max"] = max(score_distribution["max"], score)
                    
                    if score < min_score:
                        logger.debug(
                            f"[{correlation_id}] Skipping result below min_score",
                            extra={
                                'context': {
                                    'score': score,
                                    'min_score': min_score
                                }
                            }
                        )
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
                        
                        # Get URL from metadata
                        file_url = getattr(entity, "url", None)
                        result_dict["file_url"] = file_url or None
                        result_dict["url"] = file_url or None
                        
                    except AttributeError:
                        # Fallback to dictionary access
                        logger.debug(
                            f"[{correlation_id}] Using dictionary access for entity fields",
                            extra={'context': {'reason': 'getattr failed'}}
                        )
                        
                        try:
                            result_dict["chunk_id"] = entity.get("chunk_id", "")
                            result_dict["file_name"] = entity.get("file_name", "")
                            result_dict["text"] = entity.get("text", "")
                            result_dict["parent_title"] = entity.get("parent_title", "")
                            result_dict["parent_type"] = entity.get("parent_type", "")
                            result_dict["chunk_index"] = entity.get("chunk_index", 0)
                            result_dict["parent_index"] = entity.get("parent_index", 0)
                            result_dict["child_index"] = entity.get("child_index", 0)
                            
                            file_url = entity.get("url")
                            result_dict["file_url"] = file_url or None
                            result_dict["url"] = file_url or None
                        except Exception as e:
                            logger.warning(
                                f"[{correlation_id}] ⚠ Could not extract full entity data",
                                extra={
                                    'error_details': {
                                        'error_type': type(e).__name__,
                                        'error_message': str(e),
                                        'entity_type': type(entity).__name__
                                    }
                                }
                            )
                            result_dict.update({
                                "chunk_id": "",
                                "file_name": "",
                                "text": str(entity) if entity else "",
                                "parent_title": "",
                                "parent_type": "",
                                "chunk_index": 0,
                                "parent_index": 0,
                                "child_index": 0,
                                "file_url": None,
                                "url": None
                            })
                    
                    processed_results.append(result_dict)
            
            # Calculate average score
            if processed_results:
                score_distribution["avg"] = sum(r["score"] for r in processed_results) / len(processed_results)
            
            logger.info(
                f"[{correlation_id}] ✓ Milvus search completed successfully",
                extra={
                    'context': {
                        'results_count': len(processed_results),
                        'search_duration_seconds': search_duration,
                        'score_distribution': score_distribution,
                        'min_score_threshold': min_score,
                        'requested_top_k': top_k
                    }
                }
            )
            
            return processed_results
            
        except RuntimeError as e:
            logger.error(
                f"[{correlation_id}] ✗ Milvus search failed - Collection not initialized",
                extra={
                    'error_details': {
                        'error_type': 'RuntimeError',
                        'error_message': str(e),
                        'stack_trace': traceback.format_exc(),
                        'collection_name': self.collection_name,
                        'recovery_action': 'Reinitialize Milvus connection'
                    }
                },
                exc_info=True
            )
            raise
            
        except Exception as e:
            logger.error(
                f"[{correlation_id}] ✗ Milvus search failed",
                extra={
                    'error_details': {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': traceback.format_exc(),
                        'collection_name': self.collection_name,
                        'embedding_dimension': len(embedding),
                        'top_k': top_k,
                        'min_score': min_score,
                        'recovery_action': 'Will retry with exponential backoff'
                    }
                },
                exc_info=True
            )
            raise
    
    def get_collection_stats(self, correlation_id: str = None) -> Dict[str, Any]:
        """Get collection statistics with logging"""
        if not correlation_id:
            correlation_id = f"stats_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        logger.debug(
            f"[{correlation_id}] Retrieving collection stats",
            extra={'context': {'collection_name': self.collection_name}}
        )
        
        try:
            if self.collection is None:
                logger.warning(
                    f"[{correlation_id}] ⚠ Collection not initialized",
                    extra={'context': {'collection_name': self.collection_name}}
                )
                return {"error": "Collection not initialized"}
            
            stats = {
                "name": self.collection_name,
                "num_entities": self.collection.num_entities,
                "schema": str(self.collection.schema)
            }
            
            logger.debug(
                f"[{correlation_id}] ✓ Collection stats retrieved",
                extra={'context': stats}
            )
            
            return stats
            
        except Exception as e:
            logger.error(
                f"[{correlation_id}] ✗ Failed to get collection stats",
                extra={
                    'error_details': {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'collection_name': self.collection_name
                    }
                },
                exc_info=True
            )
            return {"error": str(e)}
    
    def close(self, correlation_id: str = None):
        """Close Milvus connection with logging"""
        if not correlation_id:
            correlation_id = f"close_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        logger.info(
            f"[{correlation_id}] Closing Milvus connection",
            extra={'context': {'collection_name': self.collection_name}}
        )
        
        try:
            if self.collection:
                self.collection.release()
                logger.debug(f"[{correlation_id}] Collection released")
            
            connections.disconnect("default")
            
            logger.info(
                f"[{correlation_id}] ✓ Milvus connection closed successfully",
                extra={'context': {'collection_name': self.collection_name}}
            )
            
        except Exception as e:
            logger.error(
                f"[{correlation_id}] ✗ Error closing Milvus connection",
                extra={
                    'error_details': {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': traceback.format_exc()
                    }
                },
                exc_info=True
            )