"""
Unit tests for BGEEmbeddingGenerator (BGE-M3 via FlagEmbedding)

All tests are fully mocked:
- No real model loading
- No GPU required
- CI/CD safe
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from src.processors.embedder import BGEEmbeddingGenerator


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def fake_encode_return(batch_size=1):
    """Create a fake encode() return structure."""
    return {
        "dense_vecs": np.ones((batch_size, 1024)),
        "lexical_weights": [{} for _ in range(batch_size)],
        "colbert_vecs": np.ones((batch_size, 5, 1024))
    }


# -------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------

@patch("src.processors.embedder.BGEM3FlagModel")
def test_bge_embedder_initialization(mock_model):
    """Model initializes with valid configuration."""
    embedder = BGEEmbeddingGenerator(
        embedding_type="dense",
        batch_size=8
    )

    assert embedder.embedding_type == "dense"
    assert embedder.batch_size == 8
    assert embedder.model is not None


def test_invalid_embedding_type():
    """Invalid embedding type raises ValueError."""
    with pytest.raises(ValueError):
        BGEEmbeddingGenerator(embedding_type="invalid")


@patch("src.processors.embedder.BGEM3FlagModel")
def test_encode_batch_structure(mock_model):
    """_encode_batch returns expected embedding keys."""
    fake_model = MagicMock()
    fake_model.encode.return_value = fake_encode_return(batch_size=2)
    mock_model.return_value = fake_model

    embedder = BGEEmbeddingGenerator()
    result = embedder._encode_batch(["text one", "text two"])

    assert "dense_vecs" in result
    assert "lexical_weights" in result
    assert "colbert_vecs" in result
    assert result["dense_vecs"].shape == (2, 1024)


def test_process_dense_embeddings():
    """Dense embeddings are converted to lists."""
    embedder = BGEEmbeddingGenerator(embedding_type="dense")

    raw = {
        "dense_vecs": np.ones((2, 1024)),
        "lexical_weights": [],
        "colbert_vecs": []
    }

    result = embedder._process_embeddings(raw, "dense")

    assert isinstance(result, list)
    assert len(result) == 2
    assert len(result[0]) == 1024


def test_process_sparse_embeddings():
    """Sparse embeddings are preserved as dictionaries."""
    embedder = BGEEmbeddingGenerator(embedding_type="sparse")

    raw = {
        "dense_vecs": [],
        "lexical_weights": [{"law": 1.0}, {"court": 0.5}],
        "colbert_vecs": []
    }

    result = embedder._process_embeddings(raw, "sparse")

    assert isinstance(result, list)
    assert isinstance(result[0], dict)


def test_process_colbert_embeddings():
    """ColBERT embeddings are converted correctly."""
    embedder = BGEEmbeddingGenerator(embedding_type="colbert")

    raw = {
        "dense_vecs": [],
        "lexical_weights": [],
        "colbert_vecs": np.ones((2, 5, 1024))
    }

    result = embedder._process_embeddings(raw, "colbert")

    assert isinstance(result, list)
    assert isinstance(result[0], list)
    assert len(result[0][0]) == 1024


@patch("src.processors.embedder.BGEM3FlagModel")
def test_embed_chunks_dense(mock_model):
    """embed_chunks adds dense embeddings to chunks."""
    fake_model = MagicMock()
    fake_model.encode.return_value = fake_encode_return(batch_size=1)
    mock_model.return_value = fake_model

    embedder = BGEEmbeddingGenerator(embedding_type="dense")

    chunks = [
        {"chunk_id": "c1", "text": "Lov om vaktvirksomhet"}
    ]

    result = embedder.embed_chunks(chunks)

    assert "embedding" in result[0]
    assert result[0]["embedding_type"] == "dense"
    assert len(result[0]["embedding"]) == 1024


@patch("src.processors.embedder.BGEM3FlagModel")
def test_embed_chunks_empty_text(mock_model):
    """Empty text chunks return embedding=None."""
    mock_model.return_value = MagicMock()

    embedder = BGEEmbeddingGenerator()

    chunks = [{"chunk_id": "c1", "text": ""}]
    result = embedder.embed_chunks(chunks)

    assert result[0]["embedding"] is None
    assert result[0]["embedding_type"] == "dense"


@patch("src.processors.embedder.BGEM3FlagModel")
def test_embed_text(mock_model):
    """embed_text returns a single embedding."""
    fake_model = MagicMock()
    fake_model.encode.return_value = fake_encode_return(batch_size=1)
    mock_model.return_value = fake_model

    embedder = BGEEmbeddingGenerator()

    embedding = embedder.embed_text("Norwegian legal text")

    assert isinstance(embedding, list)
    assert len(embedding) == 1024


def test_get_embedding_info():
    """Embedding configuration info is correct."""
    embedder = BGEEmbeddingGenerator()

    info = embedder.get_embedding_info()

    assert info["model_name"] == "BAAI/bge-m3"
    assert info["embedding_type"] == "dense"
    assert info["dimension"] == 1024