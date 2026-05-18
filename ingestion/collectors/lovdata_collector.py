### This code is the main Lovdata collector that fetches XML files from the LOVDATA_API_URL .
# import os
# import tarfile
# import requests
# import logging
# import xml.etree.ElementTree as ET
# import re
# import hashlib
# from ingestion.src.storage.supabase_store import SupabaseStore
# from pathlib import Path
# from typing import List, Tuple, Dict, Optional

# logger = logging.getLogger("lovdata-collector")

# from ingestion.src.config import LOVDATA_API_URL, RAW_XML_DIR, ARCHIVE_DIR

# BASE_URL = LOVDATA_API_URL

# # --------------------------------------------------
# # Small helpers
# # --------------------------------------------------
# def _is_safe_path(name: str) -> bool:
#     return ".." not in Path(name).parts


# def _is_valid_xml(data: bytes) -> bool:
#     try:
#         ET.fromstring(data)
#         return True
#     except ET.ParseError:
#         return False

# def _extract_year_from_filename(filename: str) -> Optional[int]:
#     """
#     Extract year from filename.
#     Example:
#         nl-20230614-001.xml -> 2023
#     """
#     match = re.search(r'-(\d{4})\d{4}-', filename)
#     if match:
#         return int(match.group(1))
#     return None

# # --------------------------------------------------
# # NEW: Fetch ALL archives from API
# # --------------------------------------------------
# def _fetch_all_archives() -> List[Dict]:
#     """
#     Fetch ALL available archives from Lovdata API.
    
#     Returns:
#         List of dicts with archive info:
#         [
#             {"filename": "lovtidend-avd1-2001-2025.tar.bz2", ...},
#             {"filename": "lovtidend-avd1-2026.tar.bz2", ...},
#             {"filename": "gjeldende-lover.tar.bz2", ...},
#         ]
#     """
#     try:
#         logger.info("📡 Fetching ALL archives from Lovdata API...")
        
#         resp = requests.get(f"{LOVDATA_API_URL}/list", timeout=30)
#         resp.raise_for_status()
        
#         archives = resp.json()
        
#         if not archives:
#             logger.error("❌ No archives returned from API")
#             return []
        
#         logger.info(f"✅ Found {len(archives)} archives:")
#         for archive in archives:
#             size_gb = archive.get('size', 0) / (1024**3)
#             logger.info(f"   📦 {archive['filename']}")
        
#         return archives
    
#     except Exception as e:
#         logger.error(f"❌ API call failed: {e}")
#         # Fallback to known archives
#         logger.warning("⚠️  Using fallback archive list")
#         return [
#             {"filename": "lovtidend-avd1-2001-2025.tar.bz2"},
#             {"filename": "lovtidend-avd1-2026.tar.bz2"},
#             {"filename": "gjeldende-lover.tar.bz2"},
#         ]


# # --------------------------------------------------
# # Download archive
# # --------------------------------------------------
# def _download_archive(archive_name: str) -> Path:
#     ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

#     archive_path = ARCHIVE_DIR / archive_name

#     if archive_path.exists():
#         logger.info(f"✅ Using cached: {archive_name}")
#         return archive_path

#     # ✅ Correct Lovdata download URL
#     url = f"{LOVDATA_API_URL}/get/{archive_name}"

#     logger.info(f"⬇️  Downloading: {archive_name}")
#     logger.info(f"   URL: {url}")

#     with requests.get(url, stream=True, timeout=120) as r:
#         r.raise_for_status()
#         with open(archive_path, "wb") as f:
#             for chunk in r.iter_content(8192):
#                 f.write(chunk)
                
#     if archive_path.stat().st_size < 1024:
#         logger.error("❌ Downloaded archive too small — likely corrupted")
#         archive_path.unlink(missing_ok=True)
#         raise RuntimeError("Downloaded archive too small")

#     logger.info(f"✅ Downloaded: {archive_name}")
#     return archive_path

# # --------------------------------------------------
# # Extract XML files
# # --------------------------------------------------
# def _extract_xml_files(
#     archive_path: Path,
#     limit: Optional[int] = None
# ) -> List[Path]:
#     """
#     Extract XML files from archive.
    
#     Args:
#         archive_path: Path to archive
#         limit: Max files to extract (None = extract all)
#     """
#     if limit is not None and limit == 0:
#         return []
    
#     RAW_XML_DIR.mkdir(parents=True, exist_ok=True)
#     extracted: List[Path] = []
#     db = SupabaseStore()
#     existing_hashes = db.get_all_file_hashes()  # ✅ hash-based, not name-based

    
#     try:
#         tar = tarfile.open(archive_path, "r:bz2")
#         try:
#             for member in tar.getmembers():
                
#                 if not _is_safe_path(member.name):
#                     raise ValueError(f"Unsafe path: {member.name}")
                
#                 if not member.isfile() or not member.name.endswith(".xml"):
#                     continue
                
#                 # Check limit
#                 if limit is not None and len(extracted) >= limit:
#                     break
                
#                 original_name = os.path.basename(member.name)      # nl-20010105-001.xml
#                 clean_name = os.path.splitext(original_name)[0]    # nl-20010105-001

#                 # -------- YEAR FILTER (2016–2026 ONLY) --------
#                 year = _extract_year_from_filename(original_name)

#                 if year is None or year < 2016 or year > 2026:
#                     continue


#                 target = RAW_XML_DIR / original_name              # ✅ keep .xml locally

#                 file_obj = tar.extractfile(member)
#                 if not file_obj:
#                     continue
                
#                 data = file_obj.read()
#                 if not _is_valid_xml(data):
#                     continue

#                 #   UNCHANGED = same hash in DB  → skip (already up to date)
#                 #   UPDATED   = same name, new hash → extract (reprocess)
#                 #   NEW       = never seen before  → extract
#                 data_hash = hashlib.sha256(data).hexdigest()
#                 if existing_hashes and data_hash in existing_hashes:
#                     logger.info(f"⏭️ Unchanged content, skipping: {clean_name}")
#                     continue
                
#                 with open(target, "wb") as f:
#                     f.write(data)
                
#                 extracted.append(target)
        
#         finally:
#             tar.close()
        
#         return extracted
    
#     except Exception as e:
#         logger.error(f"❌ Extraction failed: {e}")
#         # ✅ delete corrupted archive so next run re-downloads it
#         try:
#             if archive_path.exists():
#                 archive_path.unlink()
#                 logger.warning(
#                     f"🗑️ Deleted corrupted archive: {archive_path.name}. "
#                     "Will re-download next run."
#                 )
#         except Exception as cleanup_error:
#             logger.error(f"Failed to delete corrupted archive: {cleanup_error}")

#         raise

# # --------------------------------------------------
# # Public API - NEW VERSION (processes ALL archives)
# # --------------------------------------------------
# def fetch_lovdata_files(
#     limit: Optional[int] = None
# ) -> Tuple[List[str], List[str]]:
#     """
#     Fetch XML files from ALL Lovdata archives.
    
#     ✅ CHANGES:
#     - Fetches from ALL archives (not just one)
#     - No default limit (processes everything)
#     - Returns list of processed archive names
    
#     Args:
#         limit: Total files across ALL archives (None = unlimited)
        
#     Returns:
#         Tuple of:
#         - List of XML file paths
#         - List of archive names processed
    
#     Examples:
#         # Process ALL files from ALL archives
#         files, archives = fetch_lovdata_files()
        
#         # Process first 500 files total
#         files, archives = fetch_lovdata_files(limit=500)
#     """
#     if limit is not None and limit < 0:
#         raise ValueError("limit must be >= 0 or None")
    
#     # Fetch ALL available archives
#     archive_list = _fetch_all_archives()
    
#     if not archive_list:
#         logger.error("❌ No archives available")
#         return [], []
    
#     logger.info(f"\n{'='*70}")
#     logger.info(f"📦 MULTI-ARCHIVE COLLECTION")
#     logger.info(f"{'='*70}")
#     logger.info(f"Archives available: {len(archive_list)}")
#     logger.info(f"File limit: {'UNLIMITED' if limit is None else limit}")
#     logger.info(f"{'='*70}\n")
    
#     all_files: List[Path] = []
#     processed_archives: List[str] = []
#     remaining = limit

#     # -------- SIZE STATISTICS --------
#     total_size_bytes = 0
#     largest_file = 0
#     smallest_file = None

    
#     # Process each archive
#     for i, archive_info in enumerate(archive_list, 1):
#         archive_name = archive_info['filename']
        
#         logger.info(f"[{i}/{len(archive_list)}] {archive_name}")
        
#         try:
#             # Download
#             archive_path = _download_archive(archive_name)
            
#             # Calculate per-archive limit
#             if remaining is not None:
#                 if remaining <= 0:
#                     logger.info(f"⏭️  Limit reached ({limit} files), stopping")
#                     break
#                 per_archive_limit = remaining
#             else:
#                 per_archive_limit = None
            
#             # Extract
#             files = _extract_xml_files(archive_path, per_archive_limit)
            
#             if files:
#                 all_files.extend(files)
#                 processed_archives.append(archive_name)

#                 for f in files:
#                     size = Path(f).stat().st_size

#                     total_size_bytes += size

#                     if size > largest_file:
#                         largest_file = size

#                     if smallest_file is None or size < smallest_file:
#                         smallest_file = size

#                 logger.info(f"   ✅ {len(files)} files | Total: {len(all_files)}")

#                 if remaining is not None:
#                     remaining -= len(files)
#             else:
#                 logger.warning(f"   ⚠️  No files extracted")

        
#         except Exception as e:
#             logger.error(f"   ❌ Failed: {e}")
#             continue
    
#     # Summary
#     logger.info(f"\n{'='*70}")
#     logger.info(f"✅ COLLECTION COMPLETE")
#     logger.info(f"{'='*70}")
#     logger.info(f"Archives processed: {len(processed_archives)}/{len(archive_list)}")
#     logger.info(f"Total files: {len(all_files)}")
#     avg_size = (
#     total_size_bytes / len(all_files)
#     if len(all_files) > 0 else 0
#     )

#     smallest_kb = (smallest_file / 1024) if smallest_file else 0
#     largest_mb = (largest_file / (1024**2)) if largest_file else 0

#     logger.info("\n" + "="*70)
#     logger.info("📊 FILE SIZE SUMMARY")
#     logger.info("="*70)
#     logger.info(f"TOTAL FILES: {len(all_files):,}")
#     logger.info(f"TOTAL SIZE: {total_size_bytes / (1024**3):.2f} GB")
#     logger.info(f"AVERAGE SIZE: {avg_size / 1024:.2f} KB")
#     logger.info(f"LARGEST FILE: {largest_mb:.2f} MB")
#     logger.info(f"SMALLEST FILE: {smallest_kb:.2f} KB")
#     logger.info("="*70)


#     for archive_name in processed_archives:
#         logger.info(f"   ✅ {archive_name}")
#     logger.info(f"{'='*70}\n")
    
#     return [str(p) for p in all_files], processed_archives
# ----------------------------------------------------------

"""
collectors/lovdata_collector.py
================================
Scrapes Lovdata URLs from an Excel sheet and fetches the corresponding
XML documents from the Lovdata API, saving them to the raw XML directory.

Flow
----
  1. Receives the XL sheet path selected by the user (from main.py).
  2. Displays which sheet is being used — TL requirement.
  3. Extracts all lovdata.no URLs from that sheet.
  4. Fetches each URL and scrapes rich content (title, metadata, sections,
     paragraphs, tables, lists, full text).
  5. Saves structured XML to scraped_xml_1/<stem>.xml.
  6. Already-present files are skipped (idempotent).
"""

import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import requests
from bs4 import BeautifulSoup

from ingestion.src.config import RAW_XML_DIR
from ingestion.src.processors.xl_metadata_loader import load_xl_single_file

logger = logging.getLogger(__name__)

_REQUEST_DELAY_SECS = 0.5
_REQUEST_TIMEOUT    = 30


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _url_to_stem(url: str) -> Optional[str]:
    """
    Derive XML file stem from a Lovdata URL.

    https://lovdata.no/lov/1997-06-13-44             → nl-19970613-0044
    https://lovdata.no/forskrift/2016-08-12-974      → sf-20160812-0974
    https://lovdata.no/dokument/NL/lov/1997-06-13-44 → nl-19970613-0044
    """
    url = url.strip().rstrip("/").split("?")[0]
    url = url.replace("/dokument/NL/lov/",       "/lov/")
    url = url.replace("/dokument/SF/forskrift/", "/forskrift/")
    m = re.search(r'/(lov|forskrift)/(\d{4})-(\d{2})-(\d{2})(?:-(\d+))?$', url)
    if not m:
        return None
    law_type, year, month, day, num = m.groups()
    prefix = "nl" if law_type == "lov" else "sf"
    return (
        f"{prefix}-{year}{month}{day}-{int(num):04d}"
        if num
        else f"{prefix}-{year}{month}{day}"
    )


def _is_lovdata_url(url: str) -> bool:
    return "lovdata.no" in url


# ---------------------------------------------------------------------------
# Rich content extraction (ported from friend's WorkingLovdataScraper)
# ---------------------------------------------------------------------------

def _extract_title(soup: BeautifulSoup, main) -> str:
    """Extract document title from h1 tag."""
    h1 = main.find("h1")
    if h1:
        return h1.get_text(strip=True)
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
        if title not in ("Hovedmeny", "Verktøylinje", "Brukerveiledning"):
            return title
    return ""


def _extract_page_metadata(soup: BeautifulSoup, main) -> Dict[str, str]:
    """Extract <meta> tags and dl/dt/dd structures."""
    metadata: Dict[str, str] = {}

    for meta in soup.find_all("meta"):
        name    = meta.get("name") or meta.get("property")
        content = meta.get("content")
        if name and content:
            metadata[name] = content

    for dl in main.find_all("dl"):
        for dt in dl.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if dd:
                key   = dt.get_text(strip=True)
                value = dd.get_text(strip=True)
                if key and value:
                    metadata[key] = value

    return metadata


def _extract_sections(main) -> List[Dict[str, str]]:
    """Extract all div/section blocks that contain a heading."""
    sections = []

    for elem in main.find_all(["div", "section"]):
        title = ""
        for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            h = elem.find(tag)
            if h:
                title = h.get_text(strip=True)
                break

        content = elem.get_text(strip=True)
        if title and content and len(content) > 50:
            sections.append({
                "title":   title,
                "id":      elem.get("id", ""),
                "classes": " ".join(elem.get("class", [])),
                "content": content,
            })

    if not sections:
        sections.append({
            "title":   _extract_title(None, main) if main else "",
            "id":      "",
            "classes": "",
            "content": main.get_text(strip=True) if main else "",
        })

    return sections


def _extract_paragraphs(main) -> List[Dict[str, Any]]:
    """Extract <p> tags and leaf <div> blocks with substantial text."""
    paragraphs = []

    for idx, p in enumerate(main.find_all("p"), 1):
        text = p.get_text(strip=True)
        if text and len(text) > 10:
            paragraphs.append({
                "index":   idx,
                "id":      p.get("id", ""),
                "classes": " ".join(p.get("class", [])),
                "text":    text,
            })

    for div in main.find_all("div"):
        if not div.find("div"):
            text = div.get_text(strip=True)
            if text and 20 < len(text) < 1000:
                paragraphs.append({
                    "index":   len(paragraphs) + 1,
                    "id":      div.get("id", ""),
                    "classes": " ".join(div.get("class", [])),
                    "text":    text,
                })

    return paragraphs


def _extract_tables(main) -> List[Dict[str, Any]]:
    """Extract all <table> elements with headers and rows."""
    tables = []

    for idx, table in enumerate(main.find_all("table"), 1):
        entry: Dict[str, Any] = {
            "index":   idx,
            "id":      table.get("id", ""),
            "caption": "",
            "headers": [],
            "rows":    [],
        }

        caption = table.find("caption")
        if caption:
            entry["caption"] = caption.get_text(strip=True)

        for th in table.find_all("th"):
            entry["headers"].append(th.get_text(strip=True))

        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if cells:
                entry["rows"].append([c.get_text(strip=True) for c in cells])

        if entry["rows"]:
            tables.append(entry)

    return tables


def _extract_lists(main) -> List[Dict[str, Any]]:
    """Extract all <ul> and <ol> elements."""
    lists = []

    for idx, lst in enumerate(main.find_all(["ul", "ol"]), 1):
        entry: Dict[str, Any] = {
            "index":   idx,
            "type":    lst.name,
            "id":      lst.get("id", ""),
            "classes": " ".join(lst.get("class", [])),
            "items":   [],
        }

        for li in lst.find_all("li", recursive=False):
            text = li.get_text(strip=True)
            if text:
                entry["items"].append(text)

        if entry["items"]:
            lists.append(entry)

    return lists


def _extract_full_text(main) -> str:
    """Strip scripts/styles and return clean line-joined text."""
    for elem in main(["script", "style"]):
        elem.decompose()
    lines = [
        line.strip()
        for line in main.get_text(separator="\n", strip=True).split("\n")
        if line.strip()
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# XML builder
# ---------------------------------------------------------------------------

def _escape_xml(text: str) -> str:
    """Escape characters that would break XML."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


def _build_xml(
    lovdata_url: str,
    scraped:     Dict[str, Any],
    xl_meta:     Optional[Any] = None,   # XlFileMetadata or None
) -> str:
    """
    Assemble the full structured XML string from scraped content.

    Writes the <metadata> block in the format expected by text_processor.py:
      <id>, <type>, <korttittel>, <fulltittel>, <dato>, <url>, <status>

    xl_meta is an XlFileMetadata instance from xl_metadata_loader — it carries
    sub_domain_name (used as korttittel) and source_type (used as type).
    These fields are read back by text_processor.parse_lovdata_xml().
    """
    now = scraped.get("scraped_at", datetime.now().isoformat())

    # Pull XL-supplied fields (safe defaults if not provided)
    sub_domain = getattr(xl_meta, "sub_domain_name", "") if xl_meta else ""
    source_type = getattr(xl_meta, "source_type",    "") if xl_meta else ""

    lines: List[str] = ['<?xml version="1.0" encoding="utf-8"?>']
    lines.append("<document>")

    # ── metadata — matches text_processor.parse_lovdata_xml() expectations ──
    lines.append("  <metadata>")
    lines.append(f"    <id></id>")                                          # not in XL; left blank
    lines.append(f"    <type>{_escape_xml(source_type)}</type>")
    lines.append(f"    <korttittel>{_escape_xml(sub_domain)}</korttittel>")
    lines.append(f"    <fulltittel>{_escape_xml(scraped.get('title', ''))}</fulltittel>")
    lines.append(f"    <dato></dato>")                                      # not available from scrape
    lines.append(f"    <url>{_escape_xml(lovdata_url)}</url>")
    lines.append(f"    <scraped_at>{now}</scraped_at>")
    lines.append(f"    <status>{scraped.get('status', 'unknown')}</status>")
    lines.append("  </metadata>")

    if scraped.get("status") == "error":
        msg = _escape_xml(scraped.get("error_message", ""))
        lines.append(f"  <error>{msg}</error>")
        lines.append("</document>")
        return "\n".join(lines)

    # ── title ────────────────────────────────────────────────────────────
    title = _escape_xml(scraped.get("title", ""))
    lines.append(f"  <title>{title}</title>")

    # ── page metadata ────────────────────────────────────────────────────
    page_meta = scraped.get("page_metadata", {})
    if page_meta:
        lines.append("  <page_metadata>")
        for key, val in page_meta.items():
            k = _escape_xml(str(key))
            v = _escape_xml(str(val))
            lines.append(f'    <field name="{k}">{v}</field>')
        lines.append("  </page_metadata>")

    # ── sections ─────────────────────────────────────────────────────────
    sections = scraped.get("sections", [])
    lines.append(f'  <sections count="{len(sections)}">')
    for sec in sections:
        sid     = _escape_xml(sec.get("id", ""))
        classes = _escape_xml(sec.get("classes", ""))
        lines.append(f'    <section id="{sid}" classes="{classes}">')
        lines.append(f'      <title>{_escape_xml(sec.get("title", ""))}</title>')
        lines.append(f'      <content><![CDATA[{sec.get("content", "")}]]></content>')
        lines.append("    </section>")
    lines.append("  </sections>")

    # ── paragraphs ───────────────────────────────────────────────────────
    paragraphs = scraped.get("paragraphs", [])
    lines.append(f'  <paragraphs count="{len(paragraphs)}">')
    for para in paragraphs:
        idx     = para.get("index", "")
        pid     = _escape_xml(para.get("id", ""))
        classes = _escape_xml(para.get("classes", ""))
        text    = _escape_xml(para.get("text", ""))
        lines.append(f'    <paragraph index="{idx}" id="{pid}" classes="{classes}">{text}</paragraph>')
    lines.append("  </paragraphs>")

    # ── tables ───────────────────────────────────────────────────────────
    tables = scraped.get("tables", [])
    if tables:
        lines.append(f'  <tables count="{len(tables)}">')
        for tbl in tables:
            tid = _escape_xml(tbl.get("id", ""))
            lines.append(f'    <table index="{tbl["index"]}" id="{tid}">')
            if tbl.get("caption"):
                lines.append(f'      <caption>{_escape_xml(tbl["caption"])}</caption>')
            if tbl.get("headers"):
                lines.append("      <headers>")
                for h in tbl["headers"]:
                    lines.append(f"        <header>{_escape_xml(h)}</header>")
                lines.append("      </headers>")
            if tbl.get("rows"):
                lines.append("      <rows>")
                for row in tbl["rows"]:
                    lines.append("        <row>")
                    for cell in row:
                        lines.append(f"          <cell>{_escape_xml(cell)}</cell>")
                    lines.append("        </row>")
                lines.append("      </rows>")
            lines.append("    </table>")
        lines.append("  </tables>")

    # ── lists ────────────────────────────────────────────────────────────
    lists = scraped.get("lists", [])
    if lists:
        lines.append(f'  <lists count="{len(lists)}">')
        for lst in lists:
            lid     = _escape_xml(lst.get("id", ""))
            classes = _escape_xml(lst.get("classes", ""))
            lines.append(
                f'    <list index="{lst["index"]}" type="{lst["type"]}" '
                f'id="{lid}" classes="{classes}">'
            )
            for item in lst.get("items", []):
                lines.append(f"      <item>{_escape_xml(item)}</item>")
            lines.append("    </list>")
        lines.append("  </lists>")

    # ── full text ────────────────────────────────────────────────────────
    full_text = scraped.get("full_text", "")
    lines.append(f"  <full_text><![CDATA[{full_text}]]></full_text>")

    lines.append("</document>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Low-level fetch + scrape
# ---------------------------------------------------------------------------

def _fetch_xml(lovdata_url: str, xl_meta: Optional[Any] = None) -> Optional[bytes]:
    """
    Fetch a Lovdata page, scrape rich content (title, metadata, sections,
    paragraphs, tables, lists, full text) and return structured XML bytes.

    xl_meta is forwarded to _build_xml so the saved XML contains the
    korttittel / source_type fields that text_processor.py expects.
    """
    try:
        headers = {
            "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/120.0.0.0 Safari/537.36",
            "Accept":          "text/html,application/xhtml+xml,application/xml;"
                               "q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "nb,no,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection":      "keep-alive",
        }

        response = requests.get(lovdata_url, headers=headers, timeout=_REQUEST_TIMEOUT)
        response.encoding = "utf-8"

        if response.status_code != 200:
            logger.warning(f"HTTP {response.status_code} — {lovdata_url}")
            return None

        soup = BeautifulSoup(response.content, "lxml")
        main = soup.find("main", class_="docMain") or soup.find("main")

        if not main:
            logger.warning(f"No <main> element found — {lovdata_url}")
            scraped = {
                "status":        "error",
                "error_message": "No main content area found",
                "scraped_at":    datetime.now().isoformat(),
            }
            return _build_xml(lovdata_url, scraped, xl_meta).encode("utf-8")

        scraped: Dict[str, Any] = {
            "status":        "success",
            "scraped_at":    datetime.now().isoformat(),
            "title":         _extract_title(soup, main),
            "page_metadata": _extract_page_metadata(soup, main),
            "sections":      _extract_sections(main),
            "paragraphs":    _extract_paragraphs(main),
            "tables":        _extract_tables(main),
            "lists":         _extract_lists(main),
            "full_text":     _extract_full_text(main),
        }

        xml_str = _build_xml(lovdata_url, scraped, xl_meta)
        return xml_str.encode("utf-8")

    except Exception as exc:
        logger.error(f"Scraping failed — {lovdata_url}: {exc}")
        scraped = {
            "status":        "error",
            "error_message": str(exc),
            "scraped_at":    datetime.now().isoformat(),
        }
        return _build_xml(lovdata_url, scraped, xl_meta).encode("utf-8")


# ---------------------------------------------------------------------------
# Public entry point — called by main.py
# ---------------------------------------------------------------------------

def scrape_urls_from_xl(
    xl_path:    str,
    output_dir: Optional[Path] = None,
) -> List[Path]:
    """
    Read all lovdata.no URLs from *xl_path*, scrape rich content from each,
    and save structured XML to *output_dir* (defaults to RAW_XML_DIR).

    Parameters
    ----------
    xl_path    : Absolute path to the selected Excel file.
    output_dir : Where to save raw XML files. Defaults to RAW_XML_DIR.

    Returns
    -------
    List of Paths for all successfully saved (or pre-existing) XML files.
    """
    output_dir = output_dir or RAW_XML_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    xl_path_obj = Path(xl_path.replace("\\", "/"))
    if not xl_path_obj.exists():
        raise FileNotFoundError(f"Excel file not found: {xl_path_obj.resolve()}")

    domain_name, url_map = load_xl_single_file(xl_path_obj)
    if not url_map:
        logger.warning(f"No lovdata.no URLs found in: {xl_path_obj.name}")
        return []

    # ── TL requirement: show which XL sheet is being used ────────────────
    print()
    print("=" * 65)
    print("  SCRAPING LOVDATA XML FILES")
    print("=" * 65)
    print(f"  XL sheet   : {xl_path_obj.name}")
    print(f"  Domain     : {domain_name}")
    print(f"  URLs found : {len(url_map)} lovdata.no URL(s)")
    print(f"  Output     : {output_dir}")
    print("=" * 65)
    print()

    saved:        List[Path] = []
    seen_stems:   set        = set()
    count_new     = 0
    count_skipped = 0
    count_failed  = 0
    url_list      = [u for u in url_map if _is_lovdata_url(u)]
    url_total     = len(url_list)

    for url_idx, lovdata_url in enumerate(url_list, 1):
        stem = _url_to_stem(lovdata_url)
        if not stem:
            logger.debug(f"  Cannot derive stem — skipping: {lovdata_url}")
            continue

        # Deduplicate: short + long URL forms resolve to the same file
        if stem in seen_stems:
            continue
        seen_stems.add(stem)

        dest = output_dir / f"{stem}.xml"

        if dest.exists():
            print(f"  [{url_idx:>3}/{url_total}]  SKIP   {dest.name}  (already on disk)")
            count_skipped += 1
            saved.append(dest)
            continue

        print(f"  [{url_idx:>3}/{url_total}]  FETCH  {lovdata_url}")
        xl_meta = url_map.get(lovdata_url)          # XlFileMetadata for this URL
        raw_xml = _fetch_xml(lovdata_url, xl_meta)

        if raw_xml is None:
            print(f"  [{url_idx:>3}/{url_total}]  FAIL   {lovdata_url}")
            count_failed += 1
            continue

        dest.write_bytes(raw_xml)
        sections_hint = ""
        print(f"  [{url_idx:>3}/{url_total}]  SAVED  {dest.name}  ({len(raw_xml):,} bytes)")
        saved.append(dest)
        count_new += 1

        time.sleep(_REQUEST_DELAY_SECS)

    print()
    print("─" * 65)
    print(f"  Scrape done  |  new={count_new}  skipped={count_skipped}  failed={count_failed}")
    print("─" * 65)
    print()

    return saved