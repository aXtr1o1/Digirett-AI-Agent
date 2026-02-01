# ---------- PATH FIX ----------
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
# --------------------------------

# ✅ Fake boto3 BEFORE embedder import
from unittest.mock import MagicMock

fake_boto3 = MagicMock()
fake_client = MagicMock()
fake_boto3.client.return_value = fake_client
sys.modules["boto3"] = fake_boto3

import pytest
from unittest.mock import MagicMock
from ingestion.src.processors.embedder import SageMakerBGEEmbedder


def test_embedder_init():
    e = SageMakerBGEEmbedder("ep")
    assert e.endpoint_name == "ep"


def test_embed_empty_chunks():
    e = SageMakerBGEEmbedder("ep")
    assert e.embed_chunks([]) == []


def test_embed_invalid_text():
    e = SageMakerBGEEmbedder("ep")
    chunks = [{"text": "", "token_count": 0}]
    out = e.embed_chunks(chunks)
    assert out[0]["embedding"] is None


def test_invoke_batch_failure():
    e = SageMakerBGEEmbedder("ep")
    e.client.invoke_endpoint.side_effect = Exception("fail")
    assert e._invoke_batch(["x"]) == [None]


def test_embed_assigns_embedding():
    e = SageMakerBGEEmbedder("ep")
    e._invoke_batch = MagicMock(return_value=[[0.1, 0.2]])
    chunks = [{"text": "hello", "token_count": 1}]
    out = e.embed_chunks(chunks)
    assert out[0]["embedding"] is not None


def test_warn_threshold():
    e = SageMakerBGEEmbedder("ep", warn_token_threshold=1)
    e._invoke_batch = MagicMock(return_value=[[0.1]])
    e.embed_chunks([{"text": "hi", "token_count": 5}])


def test_batch_size():
    e = SageMakerBGEEmbedder("ep", batch_size=2)
    e._invoke_batch = MagicMock(return_value=[[0.1]])
    e.embed_chunks([{"text": "a", "token_count": 1}])


def test_none_text():
    e = SageMakerBGEEmbedder("ep")
    e.embed_chunks([{}])
