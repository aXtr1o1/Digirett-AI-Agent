# """
# test_collector.py  —  FIXED
# ============================
# Root cause of original error:
#     lovdata_collector.py line 377 does:
#         from ingestion.src.processors.xl_metadata_loader import load_xl_single_file
#     but that module does not exist on disk.

# Fix: stub the missing module into sys.modules BEFORE importing lovdata_collector.
# """

# import sys
# import os
# import warnings
# from unittest.mock import MagicMock, patch

# # ── PATH FIX  (must be before any project imports) ───────────────────────────
# ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# if ROOT_DIR not in sys.path:
#     sys.path.insert(0, ROOT_DIR)

# # ── Block real external clients ───────────────────────────────────────────────
# sys.modules.setdefault("supabase", MagicMock())
# sys.modules.setdefault("pymilvus", MagicMock())

# # ── Stub the missing xl_metadata_loader module ───────────────────────────────
# # lovdata_collector imports load_xl_single_file from this module at import time.
# # The module doesn't exist, so we inject a stub before the import happens.
# _xl_stub = MagicMock()
# _xl_stub.load_xl_single_file = MagicMock(return_value=("domain", {}))
# sys.modules["ingestion.src.processors.xl_metadata_loader"] = _xl_stub

# warnings.filterwarnings(
#     "ignore",
#     message="The 'strip_cdata' option of HTMLParser()*",
#     category=DeprecationWarning,
#     module="bs4",
# )

# from bs4 import BeautifulSoup
# import pytest

# from ingestion.collectors.lovdata_collector import (
#     _url_to_stem,
#     _is_lovdata_url,
#     _extract_title,
#     _extract_full_text,
#     _build_xml,
#     _fetch_xml,
#     scrape_urls_from_xl,
# )

# # ── load_xl_single_file reference used by scrape_urls_from_xl ────────────────
# # We patch the name as it is looked up INSIDE lovdata_collector's namespace.
# LOAD_XL_PATH = "ingestion.collectors.lovdata_collector.load_xl_single_file"


# # =========================================================
# # Fixtures
# # =========================================================

# @pytest.fixture
# def sample_html():
#     return """
#     <html><body>
#     <main class="docMain">
#         <h1>Test Law</h1>
#         <p>§ 1 test</p>
#     </main>
#     </body></html>
#     """


# @pytest.fixture
# def sample_scraped():
#     return {
#         "status":        "success",
#         "title":         "Test",
#         "page_metadata": {},
#         "sections":      [],
#         "paragraphs":    [],
#         "tables":        [],
#         "lists":         [],
#         "full_text":     "hello",
#     }


# # =========================================================
# # URL Helper Tests
# # =========================================================

# class TestUrlHelpers:

#     def test_url_to_stem_valid(self):
#         assert _url_to_stem(
#             "https://lovdata.no/lov/1997-06-13-44"
#         ) == "nl-19970613-0044"

#     def test_url_to_stem_forskrift(self):
#         assert _url_to_stem(
#             "https://lovdata.no/forskrift/2016-08-12-974"
#         ) == "sf-20160812-0974"

#     def test_url_to_stem_dokument_nl(self):
#         assert _url_to_stem(
#             "https://lovdata.no/dokument/NL/lov/1997-06-13-44"
#         ) == "nl-19970613-0044"

#     def test_url_to_stem_trailing_slash(self):
#         assert _url_to_stem(
#             "https://lovdata.no/lov/1997-06-13-44/"
#         ) == "nl-19970613-0044"

#     def test_url_to_stem_query_string_stripped(self):
#         assert _url_to_stem(
#             "https://lovdata.no/lov/1997-06-13-44?from=search"
#         ) == "nl-19970613-0044"

#     def test_url_to_stem_invalid(self):
#         assert _url_to_stem("https://google.com") is None

#     def test_url_to_stem_empty(self):
#         assert _url_to_stem("") is None

#     def test_is_lovdata_url_true(self):
#         assert _is_lovdata_url("https://lovdata.no/lov/1997-06-13-44") is True

#     def test_is_lovdata_url_false(self):
#         assert _is_lovdata_url("https://google.com") is False


# # =========================================================
# # HTML Extraction Tests
# # =========================================================

# class TestHtmlExtraction:

#     def test_extract_title_from_main(self):
#         soup = BeautifulSoup("<main><h1>Law Title</h1></main>", "lxml")
#         main = soup.find("main")
#         # _extract_title(soup, main_tag) — takes the full soup AND the main element
#         assert "Law Title" in _extract_title(soup, main)

#     def test_extract_title_missing(self):
#         soup = BeautifulSoup("<main></main>", "lxml")
#         main = soup.find("main")
#         result = _extract_title(soup, main)
#         assert result == "" or result is not None

#     def test_extract_full_text_basic(self):
#         soup = BeautifulSoup("<main><p>Hello world</p></main>", "lxml")
#         main = soup.find("main")
#         result = _extract_full_text(main)
#         assert "Hello world" in result

#     def test_extract_full_text_strips_scripts(self):
#         soup = BeautifulSoup(
#             "<main><script>evil()</script><p>Safe</p></main>", "lxml"
#         )
#         main = soup.find("main")
#         result = _extract_full_text(main)
#         assert "evil" not in result
#         assert "Safe" in result


# # =========================================================
# # XML Builder Tests
# # =========================================================

# class TestXmlBuilder:

#     def test_build_xml_has_xml_declaration(self, sample_scraped):
#         xml = _build_xml("https://lovdata.no/lov/1", sample_scraped)
#         assert xml.startswith('<?xml version="1.0" encoding="utf-8"?>')

#     def test_build_xml_has_metadata_block(self, sample_scraped):
#         xml = _build_xml("https://lovdata.no/lov/1", sample_scraped)
#         assert "<metadata>" in xml
#         assert "</metadata>" in xml

#     def test_build_xml_url_in_metadata(self, sample_scraped):
#         url = "https://lovdata.no/lov/1997-06-13-44"
#         xml = _build_xml(url, sample_scraped)
#         assert url in xml

#     def test_build_xml_full_text_cdata(self, sample_scraped):
#         xml = _build_xml("https://lovdata.no/lov/1", sample_scraped)
#         assert "<full_text><![CDATA[hello]]>" in xml

#     def test_build_xml_xl_meta_fields(self, sample_scraped):
#         xl_meta = MagicMock()
#         xl_meta.sub_domain_name = "Arbeidsmiljøloven"
#         xl_meta.source_type = "Lov"
#         xml = _build_xml("https://lovdata.no/lov/1", sample_scraped, xl_meta)
#         assert "<korttittel>Arbeidsmiljøloven</korttittel>" in xml
#         assert "<type>Lov</type>" in xml

#     def test_build_xml_error_status(self):
#         scraped = {
#             "status":        "error",
#             "error_message": "Connection refused",
#             "scraped_at":    "2024-01-01T00:00:00",
#         }
#         xml = _build_xml("https://lovdata.no/lov/1", scraped)
#         # The actual tag emitted is <error>…</error>, not <e>…</e>
#         assert "<error>Connection refused</error>" in xml
#         assert "<sections" not in xml

#     def test_build_xml_escapes_special_chars(self, sample_scraped):
#         sample_scraped["title"] = "<Law & Order>"
#         xml = _build_xml("https://lovdata.no/lov/1", sample_scraped)
#         assert "&lt;Law &amp; Order&gt;" in xml


# # =========================================================
# # Fetch Tests
# # =========================================================

# class TestFetchXml:

#     @patch("ingestion.collectors.lovdata_collector.requests.get")
#     def test_fetch_xml_success_returns_bytes(self, mock_get, sample_html):
#         mock_resp = MagicMock()
#         mock_resp.status_code = 200
#         mock_resp.content = sample_html.encode("utf-8")
#         mock_get.return_value = mock_resp

#         result = _fetch_xml("https://lovdata.no/lov/1997-06-13-44")
#         assert result is not None
#         assert isinstance(result, bytes)
#         assert b"<?xml" in result

#     @patch("ingestion.collectors.lovdata_collector.requests.get")
#     def test_fetch_xml_success_contains_title(self, mock_get, sample_html):
#         mock_resp = MagicMock()
#         mock_resp.status_code = 200
#         mock_resp.content = sample_html.encode("utf-8")
#         mock_get.return_value = mock_resp

#         result = _fetch_xml("https://lovdata.no/lov/1997-06-13-44")
#         assert b"Test Law" in result

#     @patch("ingestion.collectors.lovdata_collector.requests.get")
#     def test_fetch_xml_404_returns_none(self, mock_get):
#         mock_resp = MagicMock()
#         mock_resp.status_code = 404
#         mock_get.return_value = mock_resp

#         result = _fetch_xml("https://lovdata.no/lov/1997-06-13-44")
#         assert result is None

#     @patch("ingestion.collectors.lovdata_collector.requests.get")
#     def test_fetch_xml_no_main_returns_error_xml(self, mock_get):
#         mock_resp = MagicMock()
#         mock_resp.status_code = 200
#         mock_resp.content = b"<html><body><p>nothing</p></body></html>"
#         mock_get.return_value = mock_resp

#         result = _fetch_xml("https://lovdata.no/lov/1997-06-13-44")
#         assert result is not None
#         assert b"error" in result.lower()

#     @patch("ingestion.collectors.lovdata_collector.requests.get")
#     def test_fetch_xml_network_exception_returns_error_xml(self, mock_get):
#         mock_get.side_effect = Exception("timeout")

#         result = _fetch_xml("https://lovdata.no/lov/1997-06-13-44")
#         assert result is not None
#         assert b"timeout" in result

#     @patch("ingestion.collectors.lovdata_collector.requests.get")
#     def test_fetch_xml_passes_xl_meta(self, mock_get, sample_html):
#         mock_resp = MagicMock()
#         mock_resp.status_code = 200
#         mock_resp.content = sample_html.encode("utf-8")
#         mock_get.return_value = mock_resp

#         xl_meta = MagicMock()
#         xl_meta.sub_domain_name = "TestDomain"
#         xl_meta.source_type = "Forskrift"

#         result = _fetch_xml("https://lovdata.no/lov/1997-06-13-44", xl_meta)
#         assert b"TestDomain" in result
#         assert b"Forskrift" in result


# # =========================================================
# # End-to-End Scrape Tests
# # =========================================================

# class TestScrapeUrls:

#     @patch("ingestion.collectors.lovdata_collector.requests.get")
#     @patch(LOAD_XL_PATH)
#     def test_scrape_urls_saves_file(self, mock_load, mock_get, tmp_path, sample_html):
#         meta = MagicMock()
#         meta.sub_domain_name = "test"
#         meta.source_type = "Lov"

#         mock_load.return_value = (
#             "domain",
#             {"https://lovdata.no/lov/1997-06-13-44": meta},
#         )

#         mock_resp = MagicMock()
#         mock_resp.status_code = 200
#         mock_resp.content = sample_html.encode("utf-8")
#         mock_get.return_value = mock_resp

#         xl = tmp_path / "test.xlsx"
#         xl.touch()

#         result = scrape_urls_from_xl(str(xl), output_dir=tmp_path)
#         assert len(result) == 1
#         assert result[0].exists()
#         assert result[0].suffix == ".xml"

#     @patch("ingestion.collectors.lovdata_collector.requests.get")
#     @patch(LOAD_XL_PATH)
#     def test_scrape_urls_skips_existing(self, mock_load, mock_get, tmp_path, sample_html):
#         meta = MagicMock()
#         meta.sub_domain_name = "test"
#         meta.source_type = "Lov"

#         mock_load.return_value = (
#             "domain",
#             {"https://lovdata.no/lov/1997-06-13-44": meta},
#         )

#         existing = tmp_path / "nl-19970613-0044.xml"
#         existing.write_text("<document/>", encoding="utf-8")

#         xl = tmp_path / "test.xlsx"
#         xl.touch()

#         result = scrape_urls_from_xl(str(xl), output_dir=tmp_path)
#         mock_get.assert_not_called()
#         assert len(result) == 1

#     @patch(LOAD_XL_PATH)
#     def test_scrape_urls_empty_map_returns_empty(self, mock_load, tmp_path):
#         mock_load.return_value = ("domain", {})

#         xl = tmp_path / "test.xlsx"
#         xl.touch()

#         result = scrape_urls_from_xl(str(xl), output_dir=tmp_path)
#         assert result == []

#     def test_scrape_urls_missing_xl_raises(self, tmp_path):
#         with pytest.raises(FileNotFoundError):
#             scrape_urls_from_xl(
#                 str(tmp_path / "nonexistent.xlsx"), output_dir=tmp_path
#             )

#     @patch("ingestion.collectors.lovdata_collector.requests.get")
#     @patch(LOAD_XL_PATH)
#     def test_scrape_urls_deduplicates_stems(self, mock_load, mock_get, tmp_path, sample_html):
#         meta = MagicMock()
#         meta.sub_domain_name = "test"
#         meta.source_type = "Lov"

#         mock_load.return_value = (
#             "domain",
#             {
#                 "https://lovdata.no/lov/1997-06-13-44":             meta,
#                 "https://lovdata.no/dokument/NL/lov/1997-06-13-44": meta,
#             },
#         )

#         mock_resp = MagicMock()
#         mock_resp.status_code = 200
#         mock_resp.content = sample_html.encode("utf-8")
#         mock_get.return_value = mock_resp

#         xl = tmp_path / "test.xlsx"
#         xl.touch()

#         result = scrape_urls_from_xl(str(xl), output_dir=tmp_path)
#         assert len(result) == 1