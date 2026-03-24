"""
Milvus Lovdata Store - Updated with URL field support
Stores Norwegian legal document chunks with embeddings
"""

import logging
from typing import List, Dict, Any, Set
from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility
)

logger = logging.getLogger(__name__)


class MilvusLovdataStore:
    """
    Milvus vector database storage for Norwegian Lovdata documents.
    Stores hierarchical chunks with embeddings and URLs.
    """
    
    def __init__(
        self,
        milvus_host: str,
        milvus_port: int,
        collection_name: str
    ):
        """
        Initialize Milvus connection and collection.
        
        Args:
            milvus_host: Milvus server host
            milvus_port: Milvus server port
            collection_name: Name of collection to use/create
        """
        self.collection_name = collection_name
        self._processed_hashes: Set[str] = set()

        # Connect to Milvus
        connections.connect(
            alias="default",
            host=milvus_host,
            port=milvus_port
        )
        
        logger.info(f"✅ Connected to Milvus at {milvus_host}:{milvus_port}")

        # Get or create collection
        self.collection = self._get_or_create_collection()
        
        logger.info(f"✅ Collection '{collection_name}' ready")

    def _get_or_create_collection(self) -> Collection:
        """
        Get existing collection or create new one with proper schema.
        
        Returns:
            Collection object
        """
        if utility.has_collection(self.collection_name):
            logger.info(f"Loading existing collection: {self.collection_name}")
            col = Collection(self.collection_name)
            col.load()
            return col

        logger.info(f"Creating new collection: {self.collection_name}")
        
        # Define schema with all required fields
        fields = [
            # Primary key (auto-generated)
            FieldSchema(
                name="id", 
                dtype=DataType.INT64, 
                is_primary=True, 
                auto_id=True
            ),
            
            # Chunk identifier (UUID from chunker)
            FieldSchema(
                name="chunk_id", 
                dtype=DataType.VARCHAR, 
                max_length=128
            ),
            
            # File metadata
            FieldSchema(
                name="file_name", 
                dtype=DataType.VARCHAR, 
                max_length=255
            ),
            FieldSchema(
                name="file_hash", 
                dtype=DataType.VARCHAR, 
                max_length=64
            ),
            
            # Hierarchical indices
            FieldSchema(
                name="chunk_index", 
                dtype=DataType.INT64
            ),
            FieldSchema(
                name="parent_index", 
                dtype=DataType.INT64
            ),
            FieldSchema(
                name="child_index", 
                dtype=DataType.INT64
            ),
            
            # Parent metadata
            FieldSchema(
                name="parent_type", 
                dtype=DataType.VARCHAR, 
                max_length=64
            ),
            FieldSchema(
                name="parent_title", 
                dtype=DataType.VARCHAR, 
                max_length=512
            ),
            
            # Chunk content
            FieldSchema(
                name="text", 
                dtype=DataType.VARCHAR, 
                max_length=65535
            ),
            
            # ✅ NEW: Lovdata URL field
            FieldSchema(
                name="url", 
                dtype=DataType.VARCHAR, 
                max_length=512
            ),
            
            # Embedding vector (BGE-M3: 1024 dimensions)
            FieldSchema(
                name="embedding", 
                dtype=DataType.FLOAT_VECTOR, 
                dim=1024
            ),
        ]

        # Create schema
        schema = CollectionSchema(
            fields, 
            description="Norwegian Lovdata hierarchical chunks with embeddings and URLs"
        )
        
        # Create collection
        col = Collection(self.collection_name, schema)

        # Create vector index for similarity search
        logger.info("Creating HNSW index on embedding field...")
        col.create_index(
            field_name="embedding",
            index_params={
                "index_type": "HNSW",
                "metric_type": "IP",  # Inner Product (for cosine similarity)
                "params": {
                    "M": 16,  # Number of connections
                    "efConstruction": 200  # Search depth during index building
                }
            }
        )
        
        # Load collection into memory
        col.load()
        
        logger.info("✅ Collection created with HNSW index")
        
        return col

    def insert_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Insert chunks with embeddings into Milvus.
        Skips if file_hash already processed.
        
        Args:
            chunks: List of chunk dictionaries with required fields:
                - stable_chunk_id (str): UUID from chunker
                - file_name (str): Document filename
                - file_hash (str): SHA-256 hash of file
                - chunk_index (int): Sequential chunk number
                - parent_index (int): Parent section index
                - child_index (int): Child index within parent
                - parent_type (str): Type of parent (§, Kapittel, etc.)
                - parent_title (str): Parent section title
                - text (str): Chunk text content
                - url (str): Lovdata URL for this document
                - embedding (List[float]): 1024-dim embedding vector
        
        Returns:
            Dictionary with insertion result:
            - skipped (bool): True if already processed
            - inserted (int): Number of chunks inserted
            - milvus_ids (List[int]): Auto-generated primary keys
        """
        if not chunks:
            logger.warning("No chunks provided for insertion")
            return {"skipped": False, "inserted": 0}
        
        # Check if file already processed
        file_hash = chunks[0]["file_hash"]
        
        if file_hash in self._processed_hashes:
            logger.info(f"⏭️ Skipping already processed file: {chunks[0]['file_name']}")
            return {"skipped": True}
        
        # Prepare data for insertion
        # Milvus expects data as column-oriented lists
        data = [
            [c["stable_chunk_id"] for c in chunks],
            [c["file_name"] for c in chunks],
            [c["file_hash"] for c in chunks],
            [c["chunk_index"] for c in chunks],
            [c["parent_index"] for c in chunks],
            [c["child_index"] for c in chunks],
            [c["parent_type"] for c in chunks],
            [c["parent_title"] for c in chunks],
            [c["text"] for c in chunks],
            [c["url"] for c in chunks],  # ✅ NEW: URL field
            [c["embedding"] for c in chunks],
        ]
        
        try:
            # Insert into Milvus
            result = self.collection.insert(data)
            
            # Flush to ensure data is persisted
            self.collection.flush()
            
            # Mark file as processed
            self._processed_hashes.add(file_hash)
            
            logger.info(f"✅ Inserted {len(chunks)} chunks for {chunks[0]['file_name']}")
            
            return {
                "skipped": False,
                "inserted": len(chunks),
                "milvus_ids": result.primary_keys
            }
            
        except Exception as e:
            logger.error(f"❌ Error inserting chunks into Milvus: {e}")
            raise

    def search(
        self, 
        query_embedding: List[float], 
        top_k: int = 10,
        filter_expr: str = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks using vector similarity.
        
        Args:
            query_embedding: Query embedding vector (1024-dim)
            top_k: Number of results to return
            filter_expr: Optional Milvus filter expression
                         Example: 'file_name == "aksjeloven.txt"'
        
        Returns:
            List of search results with metadata and similarity scores
        """
        try:
            search_params = {
                "metric_type": "IP",
                "params": {"ef": 64}  # Search depth
            }
            
            results = self.collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=filter_expr,
                output_fields=[
                    "chunk_id", "file_name", "parent_title", 
                    "parent_type", "text", "url"  # ✅ Include URL
                ]
            )
            
            # Format results
            formatted_results = []
            for hits in results:
                for hit in hits:
                    formatted_results.append({
                        "id": hit.id,
                        "score": hit.score,
                        "chunk_id": hit.entity.get("chunk_id"),
                        "file_name": hit.entity.get("file_name"),
                        "parent_title": hit.entity.get("parent_title"),
                        "parent_type": hit.entity.get("parent_type"),
                        "text": hit.entity.get("text"),
                        "url": hit.entity.get("url")  # ✅ Include URL
                    })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"❌ Error searching Milvus: {e}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """
        Get collection statistics.
        
        Returns:
            Dictionary with collection stats
        """
        try:
            stats = {
                "collection_name": self.collection_name,
                "total_entities": self.collection.num_entities,
                "processed_files": len(self._processed_hashes)
            }
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {"error": str(e)}

    def close(self):
        """Close Milvus connection."""
        try:
            connections.disconnect("default")
            logger.info("✅ Milvus connection closed")
        except Exception as e:
            logger.error(f"Error closing Milvus connection: {e}")