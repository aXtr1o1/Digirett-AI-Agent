import sys
from unittest.mock import MagicMock

# Prevent real clients from being created
sys.modules["supabase"] = MagicMock()
sys.modules["pymilvus"] = MagicMock()
# sys.modules["boto3"] = MagicMock()


# ---------- PATH FIX ----------
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
# --------------------------------

import pytest
from ingestion.src.processors.chunker import (
    TokenCounter,
    FileHasher,
    NorwegianLovdataParser,
    NorwegianLovdataChunker
)

def test_token_counter_empty():
    assert TokenCounter().count_tokens("") == 0

def test_token_counter_estimate():
    tc = TokenCounter()
    assert tc.count_tokens("abcd") >= 1

def test_file_hash_consistent():
    h1 = FileHasher.hash_file("abc")
    h2 = FileHasher.hash_file("abc")
    assert h1 == h2

def test_generate_chunk_id_stable():
    cid1 = FileHasher.generate_chunk_id("x", 1, 1, 0)
    cid2 = FileHasher.generate_chunk_id("x", 1, 1, 0)
    assert cid1 == cid2

def test_is_separator():
    assert NorwegianLovdataParser.is_separator("------")

def test_is_metadata_false():
    assert not NorwegianLovdataParser.is_metadata_line("Random text")

def test_dynamic_parent_true():
    assert NorwegianLovdataParser.is_dynamic_parent("CHAPTER ONE:")

def test_dynamic_parent_false():
    assert not NorwegianLovdataParser.is_dynamic_parent("A")

def test_child_content_true():
    assert NorwegianLovdataParser.is_child_content(
        "This is a valid child content sentence"
    )

def test_child_content_false():
    assert not NorwegianLovdataParser.is_child_content("Too short")

def test_parse_empty_file():
    meta, parents = NorwegianLovdataParser.parse_file("", "a.txt")
    assert parents == []

def test_chunk_text_empty():
    c = NorwegianLovdataChunker()
    meta, chunks = c.chunk_text("", "a.txt")
    assert chunks == []

def test_chunk_single_text():
    c = NorwegianLovdataChunker(max_tokens=1000)
    meta, chunks = c.chunk_text("Legal text " * 10, "a.txt")
    assert len(chunks) >= 1

def test_statistics_empty():
    c = NorwegianLovdataChunker()
    stats = c.get_statistics([])
    assert stats["total_chunks"] == 0

def test_chunk_directory_empty(tmp_path):
    c = NorwegianLovdataChunker()
    assert c.chunk_directory(str(tmp_path)) == {}