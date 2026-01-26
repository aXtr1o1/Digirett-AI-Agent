"""
BGE-M3 Embedding Module for Norwegian Lovdata
Clean production version - FlagEmbedding only, no caching
"""

import logging
import torch
import numpy as np
from typing import List, Dict, Any, Union

# FlagEmbedding imports
try:
    from FlagEmbedding import BGEM3FlagModel
    FLAG_EMBEDDING_AVAILABLE = True
except ImportError:
    FLAG_EMBEDDING_AVAILABLE = False
    raise ImportError(
        "FlagEmbedding not found. Install with:\n"
        "pip install FlagEmbedding"
    )

logger = logging.getLogger(__name__)


class BGEEmbeddingGenerator:
    """
    BGE-M3 Embedding Generator for Norwegian legal text.
    
    Features:
    - Dense embeddings (semantic similarity) - 1024 dimensions
    - Sparse embeddings (lexical matching, BM25-like)
    - ColBERT embeddings (fine-grained token matching)
    - Multi-vector retrieval support
    
    Usage for Lovdata:
    - Use 'dense' for semantic search (default, recommended)
    - Use 'sparse' for exact term matching (legal citations)
    - Use 'colbert' for detailed clause matching
    - Use 'all' to get all three types
    """
    
    def __init__(
        self, 
        model_name: str = "BAAI/bge-m3",
        embedding_type: str = "dense",
        use_fp16: bool = True,
        batch_size: int = 16,
        max_length: int = 8192
    ):
        """
        Initialize BGE-M3 embedder.
        
        Args:
            model_name: Model identifier (default: BAAI/bge-m3)
            embedding_type: Type of embeddings to generate
                - 'dense': Standard vector embeddings (1024 dim)
                - 'sparse': Sparse lexical embeddings (BM25-like)
                - 'colbert': Token-level embeddings for fine-grained matching
                - 'all': Generate all three types
            use_fp16: Use half precision (faster on GPU)
            batch_size: Batch size for encoding
            max_length: Maximum sequence length (BGE-M3 supports 8192)
        """
        if not FLAG_EMBEDDING_AVAILABLE:
            raise RuntimeError("FlagEmbedding not installed")
        
        self.model_name = model_name
        self.embedding_type = embedding_type.lower()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.use_fp16 = use_fp16 and (self.device == "cuda")
        self.batch_size = batch_size
        self.max_length = max_length
        
        # Validate embedding type
        valid_types = ['dense', 'sparse', 'colbert', 'all']
        if self.embedding_type not in valid_types:
            raise ValueError(f"embedding_type must be one of {valid_types}")

        self._load_model()

    def _load_model(self):
        """Load BGE-M3 model with FlagEmbedding."""
        try:
            logger.info(f"🚀 Loading BGE-M3 via FlagEmbedding")
            logger.info(f"   Device: {self.device}")
            logger.info(f"   FP16: {self.use_fp16}")
            logger.info(f"   Embedding Type: {self.embedding_type}")
            logger.info(f"   Max Length: {self.max_length}")
            
            self.model = BGEM3FlagModel(
                self.model_name, 
                use_fp16=self.use_fp16,
                device=self.device
            )
            
            logger.info(f"✅ BGE-M3 loaded successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to load BGE-M3: {e}")
            raise

    def _encode_batch(self, texts: List[str]) -> Dict[str, Any]:
        """
        Encode texts using BGE-M3 with proper FlagEmbedding API.
        
        Returns:
            Dictionary containing:
            - 'dense_vecs': Dense embeddings (batch_size, 1024)
            - 'lexical_weights': Sparse embeddings (batch_size, vocab_size)
            - 'colbert_vecs': ColBERT embeddings (batch_size, seq_len, 1024)
        """
        try:
            embeddings = self.model.encode(
                texts,
                batch_size=self.batch_size,
                max_length=self.max_length,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=True
            )
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Error encoding batch: {e}")
            raise

    def _process_embeddings(
        self, 
        raw_embeddings: Dict[str, Any], 
        emb_type: str
    ) -> List[Any]:
        """
        Process raw embeddings based on type.
        
        Args:
            raw_embeddings: Output from model.encode()
            emb_type: 'dense', 'sparse', 'colbert', or 'all'
            
        Returns:
            List of processed embeddings (one per input text)
        """
        if emb_type == 'dense':
            return raw_embeddings['dense_vecs'].tolist()
        
        elif emb_type == 'sparse':
            return raw_embeddings['lexical_weights']
        
        elif emb_type == 'colbert':
            return [vec.tolist() for vec in raw_embeddings['colbert_vecs']]
        
        elif emb_type == 'all':
            batch_size = len(raw_embeddings['dense_vecs'])
            return [
                {
                    'dense': raw_embeddings['dense_vecs'][i].tolist(),
                    'sparse': raw_embeddings['lexical_weights'][i] if isinstance(raw_embeddings['lexical_weights'], list) else raw_embeddings['lexical_weights'],
                    'colbert': raw_embeddings['colbert_vecs'][i].tolist()
                }
                for i in range(batch_size)
            ]
        
        else:
            raise ValueError(f"Unknown embedding type: {emb_type}")

    def embed_chunks(
        self, 
        chunks: List[Any], 
        text_field: str = "text",
        show_progress: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Generate embeddings for chunks using BGE-M3.
        
        Args:
            chunks: List of Chunk objects or dictionaries
            text_field: Field name containing text to embed
            show_progress: Show progress information
            
        Returns:
            List of chunk dictionaries with embeddings added
        """
        if not chunks:
            logger.warning("No chunks provided for embedding")
            return []

        # Convert chunks to dictionaries and collect texts
        processed_chunks = []
        texts_to_embed = []
        
        for i, chunk in enumerate(chunks):
            # Handle both dataclass objects and dictionaries
            if hasattr(chunk, 'to_dict'):
                c_dict = chunk.to_dict()
            elif isinstance(chunk, dict):
                c_dict = chunk.copy()
            else:
                raise TypeError(f"Chunk must be dict or have to_dict() method, got {type(chunk)}")
            
            processed_chunks.append(c_dict)
            
            text = c_dict.get(text_field, "")
            if not text:
                logger.warning(f"Chunk {i} has no text in field '{text_field}'")
                c_dict['embedding'] = None
                c_dict['embedding_type'] = self.embedding_type
                texts_to_embed.append("")
            else:
                texts_to_embed.append(text)

        # Generate embeddings
        if show_progress:
            logger.info(f"🧠 Generating BGE-M3 embeddings ({self.embedding_type})...")
            logger.info(f"   Total chunks: {len(chunks)}")
        
        try:
            all_embeddings = []
            
            # Process in batches
            for batch_start in range(0, len(texts_to_embed), self.batch_size):
                batch_end = min(batch_start + self.batch_size, len(texts_to_embed))
                batch_texts = texts_to_embed[batch_start:batch_end]
                
                # Filter out empty texts for this batch
                valid_texts = [t for t in batch_texts if t]
                
                if not valid_texts:
                    # All texts in this batch are empty
                    all_embeddings.extend([None] * len(batch_texts))
                    continue
                
                if show_progress and len(texts_to_embed) > self.batch_size:
                    logger.info(f"   Processing batch {batch_start//self.batch_size + 1}/{(len(texts_to_embed)-1)//self.batch_size + 1}")
                
                # Get raw embeddings from model
                raw_embeddings = self._encode_batch(valid_texts)
                
                # Process based on embedding type
                batch_embeddings = self._process_embeddings(raw_embeddings, self.embedding_type)
                
                # Map back to original batch (accounting for empty texts)
                valid_idx = 0
                for text in batch_texts:
                    if text:
                        all_embeddings.append(batch_embeddings[valid_idx])
                        valid_idx += 1
                    else:
                        all_embeddings.append(None)
            
            # Add embeddings to chunks
            for i, embedding in enumerate(all_embeddings):
                processed_chunks[i]['embedding'] = embedding
                processed_chunks[i]['embedding_type'] = self.embedding_type
            
            if show_progress:
                valid_count = sum(1 for e in all_embeddings if e is not None)
                logger.info(f"✅ Embedded {valid_count} chunks successfully")
            
        except Exception as e:
            logger.error(f"❌ Error during embedding generation: {e}")
            raise

        return processed_chunks

    def embed_text(self, text: str) -> Union[List[float], Dict[str, Any]]:
        """
        Embed a single text string.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding (format depends on embedding_type)
        """
        if not text:
            logger.warning("Empty text provided for embedding")
            return None
        
        raw_embeddings = self._encode_batch([text])
        processed = self._process_embeddings(raw_embeddings, self.embedding_type)
        return processed[0]

    def get_embedding_info(self) -> Dict[str, Any]:
        """Get information about the embedding configuration."""
        return {
            "model_name": self.model_name,
            "embedding_type": self.embedding_type,
            "device": self.device,
            "use_fp16": self.use_fp16,
            "max_length": self.max_length,
            "batch_size": self.batch_size,
            "dimension": 1024 if self.embedding_type == 'dense' else 'varies'
        }