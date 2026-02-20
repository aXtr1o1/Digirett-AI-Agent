# ---------- PATH FIX ----------
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
# --------------------------------

from unittest.mock import MagicMock, patch
import pytest

# Prevent real Azure OpenAI calls by patching AzureOpenAI at import time
with patch("ingestion.src.processors.embedder.AzureOpenAI"):
    from ingestion.src.processors.embedder import TokenAwareAzureEmbedder

def make_embedder():
    """Helper: create a TokenAwareAzureEmbedder with a mocked client."""
    with patch("ingestion.src.processors.embedder.AzureOpenAI"):
        e = TokenAwareAzureEmbedder()
    e.client = MagicMock()
    return e

def test_embedder_init():
    e = make_embedder()
    assert e.deployment is not None
    assert e.batch_size is not None

def test_embed_empty_chunks():
    e = make_embedder()
    assert e.embed_chunks([]) == []


def test_embed_invalid_text():
    e = make_embedder()
    chunks = [{"text": "", "token_count": 0}]
    out = e.embed_chunks(chunks)
    assert out[0]["embedding"] is None


def test_invoke_batch_failure():
    e = make_embedder()
    e.client.embeddings.create.side_effect = Exception("fail")
    assert e._invoke_batch(["x"]) == [None]


def test_embed_assigns_embedding():
    e = make_embedder()
    e._invoke_batch = MagicMock(return_value=[[0.1, 0.2]])
    chunks = [{"text": "hello", "token_count": 1}]
    out = e.embed_chunks(chunks)
    assert out[0]["embedding"] is not None


def test_none_text():
    e = make_embedder()
    out = e.embed_chunks([{}])
    assert out[0]["embedding"] is None
