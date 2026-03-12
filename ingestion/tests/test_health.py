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

def test_is_separator():
    assert NorwegianLovdataParser.is_separator("------")

def test_is_metadata_false():
    assert not NorwegianLovdataParser.is_metadata_line("Random text")

def test_chunk_single_text():
    c = NorwegianLovdataChunker(max_tokens=1000)
    meta, chunks = c.chunk_text("Legal text " * 10, "a.txt")
    assert len(chunks) >= 1

def test_statistics_empty():
    c = NorwegianLovdataChunker()
    stats = c.get_statistics([])
    assert stats["total_chunks"] == 0
