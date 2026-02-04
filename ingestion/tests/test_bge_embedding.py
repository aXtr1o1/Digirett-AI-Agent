# ---------- PATH FIX ----------
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
# --------------------------------

from unittest.mock import MagicMock
import sys

# Prevent real AWS calls
fake_boto3 = MagicMock()
fake_client = MagicMock()
fake_boto3.client.return_value = fake_client
sys.modules["boto3"] = fake_boto3

import pytest
from ingestion.src.processors.embedder import SageMakerBGEEmbedder


def test_embedder_init():
    e = SageMakerBGEEmbedder()
    assert e.endpoint_name is not None


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


def test_none_text():
    e = SageMakerBGEEmbedder("ep")
    out = e.embed_chunks([{}])
    assert out[0]["embedding"] is None
