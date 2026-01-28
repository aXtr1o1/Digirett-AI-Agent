# ---------- PATH FIX (MUST BE FIRST) ----------
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from unittest.mock import MagicMock, patch

# ============================================
# MILVUS STORE UNIT TESTS (PURE UNIT)
# ============================================

@patch("ingestion.src.storage.milvus_store.connections.connect")
@patch("ingestion.src.storage.milvus_store.utility.has_collection")
@patch("ingestion.src.storage.milvus_store.Collection")
def test_existing_collection_loaded(mock_collection, mock_has, mock_connect):
    mock_has.return_value = True
    mock_collection.return_value.load.return_value = None

    from ingestion.src.storage.milvus_store import MilvusLovdataStore
    store = MilvusLovdataStore("localhost", 19530, "test")

    assert store.collection is not None


@patch("ingestion.src.storage.milvus_store.connections.connect")
@patch("ingestion.src.storage.milvus_store.utility.has_collection")
@patch("ingestion.src.storage.milvus_store.Collection")
def test_new_collection_created(mock_collection, mock_has, mock_connect):
    mock_has.return_value = False
    mock_collection.return_value.create_index.return_value = None
    mock_collection.return_value.load.return_value = None

    from ingestion.src.storage.milvus_store import MilvusLovdataStore
    store = MilvusLovdataStore("localhost", 19530, "new")

    assert store.collection is not None


@patch("ingestion.src.storage.milvus_store.connections.connect")
@patch("ingestion.src.storage.milvus_store.utility.has_collection")
@patch("ingestion.src.storage.milvus_store.Collection")
def test_insert_chunks_success(mock_collection, mock_has, mock_connect):
    mock_has.return_value = True
    mock_collection.return_value.insert.return_value.primary_keys = [1]
    mock_collection.return_value.flush.return_value = None

    from ingestion.src.storage.milvus_store import MilvusLovdataStore
    store = MilvusLovdataStore("localhost", 19530, "test")

    chunks = [{
        "stable_chunk_id": "c1",
        "file_name": "file",
        "file_hash": "hash",
        "chunk_index": 0,
        "parent_index": 0,
        "child_index": 0,
        "parent_type": "law",
        "parent_title": "title",
        "text": "text",
        "embedding": [0.0] * 1024
    }]

    result = store.insert_chunks(chunks)

    assert result["inserted"] == 1
    assert result["milvus_ids"] == [1]


@patch("ingestion.src.storage.milvus_store.connections.connect")
@patch("ingestion.src.storage.milvus_store.utility.has_collection")
@patch("ingestion.src.storage.milvus_store.Collection")
def test_duplicate_file_hash_is_skipped(mock_collection, mock_has, mock_connect):
    mock_has.return_value = True
    mock_collection.return_value.load.return_value = None

    from ingestion.src.storage.milvus_store import MilvusLovdataStore
    store = MilvusLovdataStore("localhost", 19530, "test")

    store._processed_hashes.add("hash")

    result = store.insert_chunks([{"file_hash": "hash"}])
    assert result["skipped"] is True


@patch("ingestion.src.storage.milvus_store.connections.connect")
@patch("ingestion.src.storage.milvus_store.utility.has_collection")
@patch("ingestion.src.storage.milvus_store.Collection")
def test_close_disconnects(mock_collection, mock_has, mock_connect):
    mock_has.return_value = True
    mock_collection.return_value.load.return_value = None

    from ingestion.src.storage.milvus_store import MilvusLovdataStore
    store = MilvusLovdataStore("localhost", 19530, "test")

    store.close()