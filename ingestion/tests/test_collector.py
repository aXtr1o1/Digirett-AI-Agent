### This file contains unit tests for the Lovdata collector module, which is responsible for fetching XML files from the LOVDATA_API_URL, validating them, and preparing them for further processing. The tests cover path safety checks, XML validation, and the logic for fetching and extracting XML files from archives. Mocking is used to isolate the tests from external dependencies and to simulate various scenarios.
# import sys
# from unittest.mock import MagicMock

# # Prevent real clients from being created
# sys.modules["supabase"] = MagicMock()
# sys.modules["pymilvus"] = MagicMock()
# # sys.modules["boto3"] = MagicMock()

# # ---------- PATH FIX (MUST BE FIRST) ----------
# import sys, os
# ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# if ROOT_DIR not in sys.path:
#     sys.path.insert(0, ROOT_DIR)
# # --------------------------------------------

# import pytest
# from unittest.mock import patch
# from pathlib import Path

# from ingestion.collectors.lovdata_collector import (
#     _is_safe_path,
#     _is_valid_xml,
#     fetch_lovdata_files
# )

# # -------------------------------------------------------------------
# # Path safety tests
# # -------------------------------------------------------------------

# def test_safe_path_valid():
#     assert _is_safe_path("file.xml")


# def test_safe_path_invalid():
#     assert not _is_safe_path("../evil.xml")


# def test_safe_path_nested():
#     assert _is_safe_path("a/b/c.xml")


# def test_safe_path_parent_ref():
#     assert not _is_safe_path("a/../b.xml")


# # -------------------------------------------------------------------
# # XML validation tests
# # -------------------------------------------------------------------

# def test_valid_xml_true():
#     assert _is_valid_xml(b"<xml>data</xml>")


# def test_valid_xml_false():
#     assert not _is_valid_xml(b"not xml")


# def test_valid_xml_empty():
#     assert not _is_valid_xml(b"")


# # -------------------------------------------------------------------
# # Fetch logic tests (REAL MULTI-ARCHIVE DESIGN)
# # -------------------------------------------------------------------

# def test_fetch_negative_limit():
#     with pytest.raises(ValueError):
#         fetch_lovdata_files(-1)


# @patch("ingestion.collectors.lovdata_collector._download_archive")
# @patch("ingestion.collectors.lovdata_collector._extract_xml_files")
# def test_fetch_single_archive(mock_extract, mock_download):
#     """
#     Should process one archive and return (files, archives)
#     """
#     mock_download.return_value = Path("a.tar.bz2")
#     mock_extract.return_value = ["file1.xml"]

#     files, archives = fetch_lovdata_files(1)

#     assert isinstance(files, list)
#     assert isinstance(archives, list)
#     assert "file1.xml" in files
#     assert len(archives) >= 1


# @patch("ingestion.collectors.lovdata_collector._download_archive")
# @patch("ingestion.collectors.lovdata_collector._extract_xml_files")
# def test_fetch_multiple_archives(mock_extract, mock_download):
#     """
#     Should accumulate files across archives and track processed archives
#     """
#     mock_download.return_value = Path("a.tar.bz2")
#     mock_extract.return_value = ["f1.xml", "f2.xml"]

#     files, archives = fetch_lovdata_files(3)

#     assert isinstance(files, list)
#     assert isinstance(archives, list)
#     assert len(files) >= 2
#     assert len(archives) >= 1


# @patch("ingestion.collectors.lovdata_collector._download_archive")
# @patch("ingestion.collectors.lovdata_collector._extract_xml_files")
# def test_fetch_no_files_extracted(mock_extract, mock_download):
#     """
#     Should gracefully handle when no XML files are extracted
#     """
#     mock_download.return_value = Path("a.tar.bz2")
#     mock_extract.return_value = []

#     files, archives = fetch_lovdata_files(2)

#     assert isinstance(files, list)
#     assert isinstance(archives, list)
#     assert len(files) == 0
#-------------------------------------------------------------------

import warnings

warnings.filterwarnings(
    "ignore",
    message="The 'strip_cdata' option of HTMLParser()*",
    category=DeprecationWarning,
    module="bs4",
)

from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup
import pytest

from collectors.lovdata_collector import (
    _url_to_stem,
    _is_lovdata_url,
    _extract_title,
    _extract_full_text,
    _build_xml,
    _fetch_xml,
    scrape_urls_from_xl
)

# =========================================================
# Fixtures
# =========================================================

@pytest.fixture
def sample_html():
    return """
    <html><body>
    <main class="docMain">
        <h1>Test Law</h1>
        <p>§ 1 test</p>
    </main>
    </body></html>
    """

@pytest.fixture
def sample_scraped():
    return {
        "status": "success",
        "title": "Test",
        "page_metadata": {},
        "sections": [],
        "paragraphs": [],
        "tables": [],
        "lists": [],
        "full_text": "hello"
    }

# =========================================================
# URL Helpers Tests
# =========================================================

class TestUrlHelpers:

    def test_url_to_stem_valid(self):
        assert _url_to_stem(
            "https://lovdata.no/lov/1997-06-13-44"
        ) == "nl-19970613-0044"

    def test_url_to_stem_invalid(self):
        assert _url_to_stem("https://google.com") is None

    def test_is_lovdata_url(self):
        assert _is_lovdata_url("https://lovdata.no/lov/1")

# =========================================================
# HTML Extraction Tests
# =========================================================

class TestHtmlExtraction:

    def test_extract_title(self):
        soup = BeautifulSoup("<main><h1>Law Title</h1></main>", "lxml")
        main = soup.find("main")
        assert _extract_title(soup, main) == "Law Title"

    def test_extract_full_text(self):
        soup = BeautifulSoup("<main><p>A</p><p>B</p></main>", "lxml")
        main = soup.find("main")
        result = _extract_full_text(main)
        assert "A" in result and "B" in result

# =========================================================
# XML Builder Tests
# =========================================================

class TestXmlBuilder:

    def test_build_xml_contains_cdata(self, sample_scraped):
        xml = _build_xml("https://lovdata.no/lov/1", sample_scraped)
        assert "<metadata>" in xml
        assert "<full_text><![CDATA[hello]]>" in xml

# =========================================================
# Fetch Tests
# =========================================================

class TestFetchXml:

    @patch("collectors.lovdata_collector.requests.get")
    def test_fetch_xml_success(self, mock_get, sample_html):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = sample_html.encode()
        mock_get.return_value = mock_resp

        result = _fetch_xml("https://lovdata.no/lov/1")
        assert result is not None
        assert b"<?xml" in result

    @patch("collectors.lovdata_collector.requests.get")
    def test_fetch_xml_404(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = _fetch_xml("https://lovdata.no/lov/1")
        assert result is None

# =========================================================
# End-to-End Scrape Tests
# =========================================================

class TestScrapeUrls:

    @patch("collectors.lovdata_collector.requests.get")
    @patch("collectors.lovdata_collector.load_xl_single_file")
    def test_scrape_urls(self, mock_load, mock_get, tmp_path, sample_html):
        meta = MagicMock()
        meta.sub_domain_name = "test"
        meta.source_type = "Lov"

        mock_load.return_value = (
            "domain",
            {"https://lovdata.no/lov/1997-06-13-44": meta}
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = sample_html.encode()
        mock_get.return_value = mock_resp

        xl = tmp_path / "test.xlsx"
        xl.touch()

        result = scrape_urls_from_xl(str(xl), output_dir=tmp_path)

        assert len(result) == 1
        assert result[0].exists()