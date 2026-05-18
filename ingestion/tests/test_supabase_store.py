"""
test_supabase_store.py  —  FIXED
==================================
Original tests called methods that don't exist in the current SupabaseStore:
  - calculate_hash         → REMOVED
  - upload_xml_to_storage  → REMOVED
  - file_exists            → REMOVED
  - get_all_file_hashes    → REMOVED

Current SupabaseStore only has:
  - _ensure_connection()
  - _find_in_table_by_file_name(table_name, file_name)
  - find_source_metadata_by_file_name(file_name)
  - download_xml_text_from_storage(bucket_path)
  - upsert_file_metadata(file_name, source_id, source_doc_url, domain,
                         subdomain, b2b_b2c, tier, jurisdiction,
                         legal_validation, xml_bucket_path, doc_title)

All tests are rewritten to match this actual API.
"""

import sys
from unittest.mock import MagicMock, patch

# Block real supabase client
sys.modules["supabase"] = MagicMock()

# ── PATH FIX ─────────────────────────────────────────────────────────────────
import os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import pytest
from ingestion.src.storage.supabase_store import SupabaseStore


# ─────────────────────────────────────────────────────────────────────────────
# _ensure_connection
# ─────────────────────────────────────────────────────────────────────────────

@patch("ingestion.src.storage.supabase_store.create_client")
def test_ensure_connection_creates_client(mock_client):
    """_ensure_connection should call create_client and set _connected."""
    s = SupabaseStore()
    assert not s._connected
    s._ensure_connection()
    assert s._connected
    assert s.supabase is not None
    mock_client.assert_called_once()


@patch("ingestion.src.storage.supabase_store.create_client")
def test_ensure_connection_idempotent(mock_client):
    """Calling _ensure_connection twice must only create the client once."""
    s = SupabaseStore()
    s._ensure_connection()
    s._ensure_connection()
    mock_client.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# find_source_metadata_by_file_name
# ─────────────────────────────────────────────────────────────────────────────

@patch("ingestion.src.storage.supabase_store.create_client")
def test_find_source_metadata_found_in_predefined(mock_client):
    """Should return row from predefined table when it exists there."""
    s = SupabaseStore()
    s._ensure_connection()

    mock_row = {"file_name": "test.xml", "source_doc_url": "https://lovdata.no/lov/1"}
    s.supabase.table().select().eq().limit().execute.return_value.data = [mock_row]

    result = s.find_source_metadata_by_file_name("test.xml")
    assert result is not None
    assert result["file_name"] == "test.xml"


@patch("ingestion.src.storage.supabase_store.create_client")
def test_find_source_metadata_not_found_returns_none(mock_client):
    """Should return None when file not found in either table."""
    s = SupabaseStore()
    s._ensure_connection()

    # Both table lookups return empty
    s.supabase.table().select().eq().limit().execute.return_value.data = []

    result = s.find_source_metadata_by_file_name("missing.xml")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# download_xml_text_from_storage
# ─────────────────────────────────────────────────────────────────────────────

@patch("ingestion.src.storage.supabase_store.create_client")
def test_download_xml_returns_string(mock_client):
    """Should decode bytes response and return a string."""
    s = SupabaseStore()
    s._ensure_connection()

    s.supabase.storage.from_().download.return_value = b"<xml>content</xml>"

    result = s.download_xml_text_from_storage("path/to/file.xml")
    assert result == "<xml>content</xml>"
    assert isinstance(result, str)


@patch("ingestion.src.storage.supabase_store.create_client")
def test_download_xml_none_response_returns_none(mock_client):
    """Should return None when storage returns None."""
    s = SupabaseStore()
    s._ensure_connection()

    s.supabase.storage.from_().download.return_value = None

    result = s.download_xml_text_from_storage("path/to/missing.xml")
    assert result is None


@patch("ingestion.src.storage.supabase_store.create_client")
def test_download_xml_exception_returns_none(mock_client):
    """Should return None (not raise) on storage exception."""
    s = SupabaseStore()
    s._ensure_connection()

    s.supabase.storage.from_().download.side_effect = Exception("network error")

    result = s.download_xml_text_from_storage("path/to/file.xml")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# upsert_file_metadata
# ─────────────────────────────────────────────────────────────────────────────

@patch("ingestion.src.storage.supabase_store.create_client")
def test_upsert_file_metadata_returns_true_on_success(mock_client):
    """Should return True when upsert succeeds."""
    s = SupabaseStore()
    s._ensure_connection()

    # upsert chain: .table().upsert().execute() — mock doesn't raise
    s.supabase.table().upsert().execute.return_value = MagicMock()

    result = s.upsert_file_metadata(
        file_name="test.xml",
        source_id="LOV-2005-06-17-62",
        source_doc_url="https://lovdata.no/lov/2005-06-17-62",
        domain="Arbeidsliv",
        subdomain="HMS",
        b2b_b2c="B2B",
        tier="1",
        jurisdiction="NO",
        legal_validation="VALIDATED",
        xml_bucket_path="bucket/test.xml",
        doc_title="Arbeidsmiljøloven",
    )
    assert result is True


@patch("ingestion.src.storage.supabase_store.create_client")
def test_upsert_file_metadata_returns_false_on_exception(mock_client):
    """Should return False (not raise) when upsert throws."""
    s = SupabaseStore()
    s._ensure_connection()

    s.supabase.table().upsert().execute.side_effect = Exception("DB error")

    result = s.upsert_file_metadata(
        file_name="test.xml",
        source_id="LOV-2005-06-17-62",
        source_doc_url="https://lovdata.no/lov/2005-06-17-62",
        domain="Arbeidsliv",
        subdomain="HMS",
        b2b_b2c="B2B",
        tier="1",
        jurisdiction="NO",
        legal_validation="VALIDATED",
        xml_bucket_path="bucket/test.xml",
        doc_title="Arbeidsmiljøloven",
    )
    assert result is False