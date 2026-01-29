# ---------- PATH FIX (MUST BE FIRST) ----------
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import tempfile
import pytest
from unittest.mock import MagicMock, patch

# ============================================
# SUPABASE STORE UNIT TESTS
# ============================================

@patch("ingestion.src.storage.supabase_store.create_client")
def test_supabase_init(mock_create_client):
    from ingestion.src.storage.supabase_store import SupabaseStore
    store = SupabaseStore()
    assert store.supabase is not None


def test_calculate_hash_creates_valid_sha256():
    from ingestion.src.storage.supabase_store import SupabaseStore
    store = SupabaseStore()

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"hello")
        path = f.name

    h1 = store.calculate_hash(path)
    h2 = store.calculate_hash(path)

    assert h1 == h2
    assert len(h1) == 64


@patch("ingestion.src.storage.supabase_store.create_client")
def test_upload_xml_to_storage_returns_public_url(mock_client):
    mock_client.return_value.storage.from_.return_value = MagicMock()

    from ingestion.src.storage.supabase_store import SupabaseStore
    store = SupabaseStore()

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"<xml></xml>")
        path = f.name

    url = store.upload_xml_to_storage(path, "file1")
    assert "/storage/v1/object/public/" in url


@patch("ingestion.src.storage.supabase_store.create_client")
def test_upload_xml_and_log_success(mock_client):
    mock_client.return_value.table.return_value = MagicMock()

    from ingestion.src.storage.supabase_store import SupabaseStore
    store = SupabaseStore()

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"<xml></xml>")
        path = f.name

    assert store.upload_xml_and_log(path, "zip1") is True


@patch("ingestion.src.storage.supabase_store.create_client")
def test_upload_xml_and_log_failure(mock_client):
    mock_client.return_value.storage.from_.side_effect = Exception("fail")

    from ingestion.src.storage.supabase_store import SupabaseStore
    store = SupabaseStore()

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"<xml></xml>")
        path = f.name

    assert store.upload_xml_and_log(path, "zip1") is False


@patch("ingestion.src.storage.supabase_store.create_client")
def test_insert_file_metadata_success(mock_client):
    from ingestion.src.storage.supabase_store import SupabaseStore
    store = SupabaseStore()

    store.insert_file_metadata(
        zip_name="zip",
        file_name="file",
        file_hash="hash",
        file_size=10,
        file_storage_uri="uri"
    )


@patch("ingestion.src.storage.supabase_store.create_client")
def test_insert_file_metadata_failure(mock_client):
    mock_client.return_value.table.return_value.insert.side_effect = Exception("db error")

    from ingestion.src.storage.supabase_store import SupabaseStore
    store = SupabaseStore()

    with pytest.raises(Exception):
        store.insert_file_metadata("zip", "file", "hash", 1, "uri")