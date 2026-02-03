# ---------- PATH FIX (MUST BE FIRST) ----------
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
# --------------------------------------------

import pytest
from unittest.mock import patch
from pathlib import Path

from ingestion.collectors.lovdata_collector import (
    _is_safe_path,
    _is_valid_xml,
    fetch_lovdata_files
)

# -------------------------------------------------------------------
# Path safety tests
# -------------------------------------------------------------------

def test_safe_path_valid():
    assert _is_safe_path("file.xml")


def test_safe_path_invalid():
    assert not _is_safe_path("../evil.xml")


def test_safe_path_nested():
    assert _is_safe_path("a/b/c.xml")


def test_safe_path_parent_ref():
    assert not _is_safe_path("a/../b.xml")


# -------------------------------------------------------------------
# XML validation tests
# -------------------------------------------------------------------

def test_valid_xml_true():
    assert _is_valid_xml(b"<xml>data</xml>")


def test_valid_xml_false():
    assert not _is_valid_xml(b"not xml")


def test_valid_xml_empty():
    assert not _is_valid_xml(b"")


# -------------------------------------------------------------------
# Fetch logic tests (REAL MULTI-ARCHIVE DESIGN)
# -------------------------------------------------------------------

def test_fetch_negative_limit():
    with pytest.raises(ValueError):
        fetch_lovdata_files(-1)


@patch("ingestion.collectors.lovdata_collector._download_archive")
@patch("ingestion.collectors.lovdata_collector._extract_xml_files")
def test_fetch_single_archive(mock_extract, mock_download):
    """
    Should process one archive and return (files, archives)
    """
    mock_download.return_value = Path("a.tar.bz2")
    mock_extract.return_value = ["file1.xml"]

    files, archives = fetch_lovdata_files(1)

    assert isinstance(files, list)
    assert isinstance(archives, list)
    assert "file1.xml" in files
    assert len(archives) == 1


@patch("ingestion.collectors.lovdata_collector._download_archive")
@patch("ingestion.collectors.lovdata_collector._extract_xml_files")
def test_fetch_multiple_archives(mock_extract, mock_download):
    """
    Should accumulate files across archives and track processed archives
    """
    mock_download.return_value = Path("a.tar.bz2")
    mock_extract.return_value = ["f1.xml", "f2.xml"]

    files, archives = fetch_lovdata_files(3)

    assert isinstance(files, list)
    assert isinstance(archives, list)
    assert len(files) >= 2
    assert len(archives) >= 1


@patch("ingestion.collectors.lovdata_collector._download_archive")
@patch("ingestion.collectors.lovdata_collector._extract_xml_files")
def test_fetch_no_files_extracted(mock_extract, mock_download):
    """
    Should gracefully handle when no XML files are extracted
    """
    mock_download.return_value = Path("a.tar.bz2")
    mock_extract.return_value = []

    files, archives = fetch_lovdata_files(2)

    assert isinstance(files, list)
    assert isinstance(archives, list)
    assert len(files) == 0
