# ---------- PATH FIX ----------
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
# --------------------------------

import pytest
from unittest.mock import patch, MagicMock
from ingestion.src.storage.milvus_store import MilvusTextStore
from ingestion.src.config import MILVUS_COLLECTION


@patch("ingestion.src.storage.milvus_store.connections.connect")
@patch("ingestion.src.storage.milvus_store.utility.has_collection", return_value=True)
@patch("ingestion.src.storage.milvus_store.Collection")
def test_milvus_init(_, __, ___):
    store = MilvusTextStore()
    assert store.collection_name == MILVUS_COLLECTION


def test_fix_embedding_list():
    s = MilvusTextStore.__new__(MilvusTextStore)
    s.embedding_dim = 3
    assert s._fix_embedding([1, 2, 3]) == [1.0, 2.0, 3.0]


def test_fix_embedding_nested():
    s = MilvusTextStore.__new__(MilvusTextStore)
    s.embedding_dim = 3
    assert s._fix_embedding([[1, 2, 3]]) == [1.0, 2.0, 3.0]


def test_fix_embedding_empty():
    s = MilvusTextStore.__new__(MilvusTextStore)
    s.embedding_dim = 3
    with pytest.raises(ValueError):
        s._fix_embedding([])


def test_fix_embedding_bad_type():
    s = MilvusTextStore.__new__(MilvusTextStore)
    s.embedding_dim = 3
    with pytest.raises(TypeError):
        s._fix_embedding("bad")


def test_fix_embedding_dimension_mismatch():
    s = MilvusTextStore.__new__(MilvusTextStore)
    s.embedding_dim = 5
    emb = [1, 2, 3]
    with pytest.raises(ValueError):
        s._fix_embedding(emb)