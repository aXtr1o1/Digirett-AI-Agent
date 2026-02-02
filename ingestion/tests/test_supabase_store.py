# ---------- PATH FIX ----------
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
# --------------------------------

import pytest
from unittest.mock import patch
from ingestion.src.storage.supabase_store import SupabaseStore

@patch("ingestion.src.storage.supabase_store.create_client")
def test_supabase_init(mock_client):
    s = SupabaseStore()
    assert s.supabase is not None

def test_hash_consistent(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("abc")
    s = SupabaseStore.__new__(SupabaseStore)
    h1 = s.calculate_hash(str(f))
    h2 = s.calculate_hash(str(f))
    assert h1 == h2

@patch("ingestion.src.storage.supabase_store.create_client")
def test_upload_duplicate(mock_client):
    s = SupabaseStore()
    s.supabase.storage.from_().list.return_value = [{"name": "x"}]
    assert s.upload_xml_to_storage("a.xml", "x.xml")

@patch("ingestion.src.storage.supabase_store.create_client")
def test_file_exists_false(mock_client):
    s = SupabaseStore()
    s.supabase.table().select().eq().limit().execute.return_value.data = []
    assert not s.file_exists("x")

@patch("ingestion.src.storage.supabase_store.create_client")
def test_get_all_hashes(mock_client):
    s = SupabaseStore()
    s.supabase.table().select().execute.return_value.data = [{"file_hash": "x"}]
    assert "x" in s.get_all_file_hashes()

@patch("ingestion.src.storage.supabase_store.create_client")
def test_cleanup(mock_client):
    s = SupabaseStore()
    s.supabase.storage.from_().list.return_value = [{"name": "a.xml"}]
    s.cleanup_duplicate_xml_files()