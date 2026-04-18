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

# NOTE: environment variables and sys.path are set up in conftest.py —
# no need to touch os.environ or sys.path here.

from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup
import pytest

from ingestion.collectors.lovdata_collector import (
    _url_to_stem,
    _is_lovdata_url,
    _extract_title,
    _extract_full_text,
    _build_xml,
    _fetch_xml,
    scrape_urls_from_xl,
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
        "status":        "success",
        "title":         "Test",
        "page_metadata": {},
        "sections":      [],
        "paragraphs":    [],
        "tables":        [],
        "lists":         [],
        "full_text":     "hello",
    }

# =========================================================
# URL Helpers Tests
# =========================================================

class TestUrlHelpers:

    def test_url_to_stem_valid(self):
        assert _url_to_stem(
            "https://lovdata.no/lov/1997-06-13-44"
        ) == "nl-19970613-0044"

    def test_url_to_stem_forskrift(self):
        assert _url_to_stem(
            "https://lovdata.no/forskrift/2016-08-12-974"
        ) == "sf-20160812-0974"

    def test_url_to_stem_dokument_nl(self):
        assert _url_to_stem(
            "https://lovdata.no/dokument/NL/lov/1997-06-13-44"
        ) == "nl-19970613-0044"

    def test_url_to_stem_trailing_slash(self):
        assert _url_to_stem(
            "https://lovdata.no/lov/1997-06-13-44/"
        ) == "nl-19970613-0044"

    def test_url_to_stem_query_string_stripped(self):
        assert _url_to_stem(
            "https://lovdata.no/lov/1997-06-13-44?from=search"
        ) == "nl-19970613-0044"

    def test_url_to_stem_invalid(self):
        assert _url_to_stem("https://google.com") is None

    def test_url_to_stem_empty(self):
        assert _url_to_stem("") is None

    def test_is_lovdata_url_true(self):
        assert _is_lovdata_url("https://lovdata.no/lov/1997-06-13-44") is True

    def test_is_lovdata_url_false(self):
        assert _is_lovdata_url("https://google.com") is False

# =========================================================
# HTML Extraction Tests
# =========================================================

class TestHtmlExtraction:

    def test_extract_title_from_main(self):
        soup = BeautifulSoup("<main><h1>Law Title</h1></main>", "lxml")
        main = soup.find("main")
        assert _extract_title(soup, main) == "Law Title"

    def test_extract_title_fallback_to_soup(self):
        """Falls back to soup-level h1 when main has none."""
        soup = BeautifulSoup("<html><h1>Fallback Title</h1><main><p>text</p></main></html>", "lxml")
        main = soup.find("main")
        assert _extract_title(soup, main) == "Fallback Title"

    def test_extract_title_empty_when_none(self):
        soup = BeautifulSoup("<main><p>no heading</p></main>", "lxml")
        main = soup.find("main")
        assert _extract_title(soup, main) == ""

    def test_extract_full_text_contains_paragraphs(self):
        soup = BeautifulSoup("<main><p>Alpha</p><p>Beta</p></main>", "lxml")
        main = soup.find("main")
        result = _extract_full_text(main)
        assert "Alpha" in result
        assert "Beta" in result

    def test_extract_full_text_strips_scripts(self):
        soup = BeautifulSoup(
            "<main><script>evil()</script><p>Safe</p></main>", "lxml"
        )
        main = soup.find("main")
        result = _extract_full_text(main)
        assert "evil" not in result
        assert "Safe" in result

# =========================================================
# XML Builder Tests
# =========================================================

class TestXmlBuilder:

    def test_build_xml_has_xml_declaration(self, sample_scraped):
        xml = _build_xml("https://lovdata.no/lov/1", sample_scraped)
        assert xml.startswith('<?xml version="1.0" encoding="utf-8"?>')

    def test_build_xml_has_metadata_block(self, sample_scraped):
        xml = _build_xml("https://lovdata.no/lov/1", sample_scraped)
        assert "<metadata>" in xml
        assert "</metadata>" in xml

    def test_build_xml_url_in_metadata(self, sample_scraped):
        url = "https://lovdata.no/lov/1997-06-13-44"
        xml = _build_xml(url, sample_scraped)
        assert url in xml

    def test_build_xml_full_text_cdata(self, sample_scraped):
        xml = _build_xml("https://lovdata.no/lov/1", sample_scraped)
        assert "<full_text><![CDATA[hello]]>" in xml

    def test_build_xml_xl_meta_fields(self, sample_scraped):
        """korttittel and type should come from xl_meta when supplied."""
        xl_meta = MagicMock()
        xl_meta.sub_domain_name = "Arbeidsmiljøloven"
        xl_meta.source_type = "Lov"
        xml = _build_xml("https://lovdata.no/lov/1", sample_scraped, xl_meta)
        assert "<korttittel>Arbeidsmiljøloven</korttittel>" in xml
        assert "<type>Lov</type>" in xml

    def test_build_xml_error_status(self):
        scraped = {
            "status":        "error",
            "error_message": "Connection refused",
            "scraped_at":    "2024-01-01T00:00:00",
        }
        xml = _build_xml("https://lovdata.no/lov/1", scraped)
        assert "<error>Connection refused</error>" in xml
        # Should NOT contain content sections on error
        assert "<sections" not in xml

    def test_build_xml_escapes_special_chars(self, sample_scraped):
        sample_scraped["title"] = "<Law & Order>"
        xml = _build_xml("https://lovdata.no/lov/1", sample_scraped)
        assert "&lt;Law &amp; Order&gt;" in xml

# =========================================================
# Fetch Tests
# =========================================================

class TestFetchXml:

    @patch("ingestion.collectors.lovdata_collector.requests.get")
    def test_fetch_xml_success_returns_bytes(self, mock_get, sample_html):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = sample_html.encode("utf-8")
        mock_get.return_value = mock_resp

        result = _fetch_xml("https://lovdata.no/lov/1997-06-13-44")
        assert result is not None
        assert isinstance(result, bytes)
        assert b"<?xml" in result

    @patch("ingestion.collectors.lovdata_collector.requests.get")
    def test_fetch_xml_success_contains_title(self, mock_get, sample_html):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = sample_html.encode("utf-8")
        mock_get.return_value = mock_resp

        result = _fetch_xml("https://lovdata.no/lov/1997-06-13-44")
        assert b"Test Law" in result

    @patch("ingestion.collectors.lovdata_collector.requests.get")
    def test_fetch_xml_404_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = _fetch_xml("https://lovdata.no/lov/1997-06-13-44")
        assert result is None

    @patch("ingestion.collectors.lovdata_collector.requests.get")
    def test_fetch_xml_no_main_returns_error_xml(self, mock_get):
        """Page with no <main> should return error XML, not None."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"<html><body><p>nothing</p></body></html>"
        mock_get.return_value = mock_resp

        result = _fetch_xml("https://lovdata.no/lov/1997-06-13-44")
        assert result is not None
        assert b"error" in result.lower()

    @patch("ingestion.collectors.lovdata_collector.requests.get")
    def test_fetch_xml_network_exception_returns_error_xml(self, mock_get):
        """Network errors should be caught and returned as error XML."""
        mock_get.side_effect = Exception("timeout")

        result = _fetch_xml("https://lovdata.no/lov/1997-06-13-44")
        assert result is not None
        assert b"timeout" in result

    @patch("ingestion.collectors.lovdata_collector.requests.get")
    def test_fetch_xml_passes_xl_meta(self, mock_get, sample_html):
        """xl_meta fields should appear in the returned XML."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = sample_html.encode("utf-8")
        mock_get.return_value = mock_resp

        xl_meta = MagicMock()
        xl_meta.sub_domain_name = "TestDomain"
        xl_meta.source_type = "Forskrift"

        result = _fetch_xml("https://lovdata.no/lov/1997-06-13-44", xl_meta)
        assert b"TestDomain" in result
        assert b"Forskrift" in result

# =========================================================
# End-to-End Scrape Tests
# =========================================================

class TestScrapeUrls:

    @patch("ingestion.collectors.lovdata_collector.requests.get")
    @patch("ingestion.collectors.lovdata_collector.load_xl_single_file")
    def test_scrape_urls_saves_file(self, mock_load, mock_get, tmp_path, sample_html):
        meta = MagicMock()
        meta.sub_domain_name = "test"
        meta.source_type = "Lov"

        mock_load.return_value = (
            "domain",
            {"https://lovdata.no/lov/1997-06-13-44": meta},
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = sample_html.encode("utf-8")
        mock_get.return_value = mock_resp

        xl = tmp_path / "test.xlsx"
        xl.touch()

        result = scrape_urls_from_xl(str(xl), output_dir=tmp_path)

        assert len(result) == 1
        assert result[0].exists()
        assert result[0].suffix == ".xml"

    @patch("ingestion.collectors.lovdata_collector.requests.get")
    @patch("ingestion.collectors.lovdata_collector.load_xl_single_file")
    def test_scrape_urls_skips_existing(self, mock_load, mock_get, tmp_path, sample_html):
        """A file already on disk should be skipped (idempotent)."""
        meta = MagicMock()
        meta.sub_domain_name = "test"
        meta.source_type = "Lov"

        mock_load.return_value = (
            "domain",
            {"https://lovdata.no/lov/1997-06-13-44": meta},
        )

        # Pre-create the output file
        existing = tmp_path / "nl-19970613-0044.xml"
        existing.write_text("<document/>", encoding="utf-8")

        xl = tmp_path / "test.xlsx"
        xl.touch()

        result = scrape_urls_from_xl(str(xl), output_dir=tmp_path)

        # requests.get should never have been called
        mock_get.assert_not_called()
        assert len(result) == 1

    @patch("ingestion.collectors.lovdata_collector.load_xl_single_file")
    def test_scrape_urls_empty_map_returns_empty(self, mock_load, tmp_path):
        mock_load.return_value = ("domain", {})

        xl = tmp_path / "test.xlsx"
        xl.touch()

        result = scrape_urls_from_xl(str(xl), output_dir=tmp_path)
        assert result == []

    def test_scrape_urls_missing_xl_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            scrape_urls_from_xl(str(tmp_path / "nonexistent.xlsx"), output_dir=tmp_path)

    @patch("ingestion.collectors.lovdata_collector.requests.get")
    @patch("ingestion.collectors.lovdata_collector.load_xl_single_file")
    def test_scrape_urls_deduplicates_stems(self, mock_load, mock_get, tmp_path, sample_html):
        """Two URL forms resolving to the same stem should produce one file."""
        meta = MagicMock()
        meta.sub_domain_name = "test"
        meta.source_type = "Lov"

        mock_load.return_value = (
            "domain",
            {
                "https://lovdata.no/lov/1997-06-13-44":              meta,
                "https://lovdata.no/dokument/NL/lov/1997-06-13-44":  meta,
            },
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = sample_html.encode("utf-8")
        mock_get.return_value = mock_resp

        xl = tmp_path / "test.xlsx"
        xl.touch()

        result = scrape_urls_from_xl(str(xl), output_dir=tmp_path)
        assert len(result) == 1