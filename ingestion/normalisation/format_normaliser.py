import logging
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_BLACKLIST = [
    "Verktøylinje",
    "Innholdsfortegnelse",
    "Ditt søk ga dessverre ingen treff",
    "Del paragraf",
    "\U0001f517", "➦", "\ue000", "\ue001", "\ue002",
    "\ue003", "\ue004", "\ue005", "\ue006", "⎙", "\ue007",
]

# Regex that strips characters illegal in XML 1.0 except tab/LF/CR
_ILLEGAL_XML_CHARS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f"
    r"\ud800-\udfff\ufffe\uffff]"
)


# ---------------------------------------------------------------------------
# XML parsing (with recovery for malformed files)
# ---------------------------------------------------------------------------

def _parse_xml(xml_path: Path) -> Optional[ET.Element]:
    """
    Try to parse XML, returning the root Element or None on failure.

    Strategy:
      1. Standard library ET.parse  (fast, strict)
      2. lxml with recover=True     (handles most real-world malformed XML)
      3. Byte-level sanitising + ET (strips illegal control characters)
    """
    # -- attempt 1: standard strict parse ------------------------------------
    try:
        return ET.parse(xml_path).getroot()
    except ET.ParseError:
        pass

    # -- attempt 2: lxml recovery -------------------------------------------
    try:
        from lxml import etree as LXML_ET  # noqa: PLC0415

        parser = LXML_ET.XMLParser(recover=True, encoding="utf-8")
        lxml_tree = LXML_ET.parse(str(xml_path), parser)
        # Serialise back to a string and re-parse with stdlib so the rest of
        # the code only ever sees ET.Element objects.
        xml_bytes = LXML_ET.tostring(lxml_tree.getroot(), encoding="unicode")
        return ET.fromstring(xml_bytes)
    except Exception:
        pass

    # -- attempt 3: strip illegal bytes then re-parse -----------------------
    try:
        raw = xml_path.read_bytes()
        # Try UTF-8 first, then latin-1 which never fails
        for enc in ("utf-8", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="replace")

        text = _ILLEGAL_XML_CHARS.sub("", text)
        return ET.fromstring(text)
    except Exception as exc:
        logger.error("Could not recover XML from %s: %s", xml_path.name, exc)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Collapse whitespace and strip UI artefacts — for single-line values."""
    if not text:
        return ""
    for bad in _BLACKLIST:
        text = text.replace(bad, "")
    return " ".join(text.split()).strip()


def _clean_multiline(text: str) -> str:
    """
    Strip UI artefacts line-by-line WITHOUT collapsing newlines.
    Used for <full_text> so that § line boundaries are preserved for chunker.
    """
    if not text:
        return ""
    cleaned_lines = []
    for line in text.splitlines():
        for bad in _BLACKLIST:
            line = line.replace(bad, "")
        line = line.strip()
        if line:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


# ---------------------------------------------------------------------------
# Extraction strategies
# ---------------------------------------------------------------------------

def _from_full_text(root: ET.Element) -> str:
    """
    PRIMARY: <full_text> CDATA block.
    Produced by BeautifulSoup get_text(separator='\n') — preserves § markers.
    """
    elem = root.find("full_text")
    if elem is None or not elem.text:
        return ""
    return _clean_multiline(elem.text)


def _from_paragraphs(root: ET.Element) -> str:
    """
    FALLBACK 1: individual <paragraph> elements sorted by index attribute.
    """
    paras = root.findall(".//paragraph")
    if not paras:
        return ""

    def _idx(p: ET.Element) -> int:
        try:
            return int(p.get("index", "0"))
        except ValueError:
            return 0

    blocks = []
    for p in sorted(paras, key=_idx):
        text = _clean_text(p.text or "")
        if text and len(text) > 10:
            blocks.append(text)

    return "\n\n".join(blocks)


def _from_sections(root: ET.Element) -> str:
    """
    FALLBACK 2: <section><content> blocks — HTML layout divs.
    Loses § structure but better than nothing.
    """
    blocks: List[str] = []
    for section in root.findall(".//section"):
        title        = _clean_text(section.findtext("title", ""))
        content_elem = section.find("content")
        content      = _clean_text(
            (content_elem.text or "") if content_elem is not None else ""
        )
        if len(content) < 30:
            continue
        if title:
            blocks.append(f"SECTION: {title}")
        blocks.append(content)
    return "\n\n".join(blocks).strip()


def _from_raw_elements(root: ET.Element) -> str:
    """
    FALLBACK 3 (last resort): walk every element and collect all text/tail.
    Returns an empty string only if the file is genuinely empty.
    """
    parts: List[str] = []
    for elem in root.iter():
        for piece in (elem.text, elem.tail):
            cleaned = _clean_text(piece or "")
            if cleaned and len(cleaned) > 5:
                parts.append(cleaned)
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_lovdata_xml(xml_path: Path) -> Dict:
    """
    Parse one Lovdata XML file into clean text + metadata dict.
    Returns {} on error or for scraper-error files.
    """
    root = _parse_xml(xml_path)

    if root is None:
        logger.error("Skipping unrecoverable XML: %s", xml_path.name)
        return {}

    try:
        # ── metadata ────────────────────────────────────────────────────
        meta = root.find("metadata")
        metadata = {
            "file_name":  xml_path.name,
            "id":         meta.findtext("id",          "") if meta is not None else "",
            "type":       meta.findtext("type",         "") if meta is not None else "",
            "korttittel": meta.findtext("korttittel",   "") if meta is not None else "",
            "fulltittel": meta.findtext("fulltittel",   "") if meta is not None else "",
            "dato":       meta.findtext("dato",          "") if meta is not None else "",
            "url":        meta.findtext("url",           "") if meta is not None else "",
        }

        # ── skip scraper-error files ─────────────────────────────────────
        status    = meta.findtext("status", "") if meta is not None else ""
        error_tag = root.find("error") or root.find("e")

        if status == "error" or (
            error_tag is not None
            and error_tag.text
            and error_tag.text.strip()
        ):
            reason = (
                error_tag.text.strip()[:120]
                if error_tag is not None and error_tag.text
                else "status=error"
            )
            logger.warning(
                "Skipping scraper-error file: %s | url=%s | reason=%s",
                xml_path.name,
                metadata["url"],
                reason,
            )
            return {}

        # ── text extraction: priority order ──────────────────────────────
        full_text = _from_full_text(root)
        source    = "full_text"

        if not full_text:
            full_text = _from_paragraphs(root)
            source    = "paragraphs"

        if not full_text:
            full_text = _from_sections(root)
            source    = "sections"

        if not full_text:
            full_text = _from_raw_elements(root)
            source    = "raw_elements"

        if not full_text:
            logger.warning("No usable text in any source: %s", xml_path.name)
            return {}

        logger.info(
            "Parsed %s | source=%s | chars=%s | lines=%s | korttittel=%r",
            xml_path.name,
            source,
            f"{len(full_text):,}",
            full_text.count("\n") + 1,
            metadata["korttittel"],
        )

        return {
            "file_name":    xml_path.name,
            "text":         full_text,
            "metadata":     metadata,
            "document_url": metadata.get("url", "").strip(),
        }

    except Exception as exc:
        logger.exception("Failed to parse %s: %s", xml_path.name, exc)
        return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_xml_to_text(
    xml_files:   List[Path],
    max_workers: int = 4,
) -> List[Dict]:
    """
    Convert a list of XML paths to clean text dicts in parallel.
    Returns only documents with non-empty text.
    """
    documents: List[Dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for result in executor.map(parse_lovdata_xml, xml_files):
            if result and result.get("text"):
                documents.append(result)

    logger.info(
        "Converted %s/%s XML file(s) to clean text",
        len(documents),
        len(xml_files),
    )
    return documents