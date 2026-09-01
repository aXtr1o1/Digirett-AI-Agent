from __future__ import annotations

import logging
import re
from typing import List, Optional
from bs4 import BeautifulSoup, NavigableString, Tag

from ingestion.models.legal_section import LegalBlock

logger = logging.getLogger(__name__)

# Configurable HTML classes to ignore (metadata, changelogs, UI widgets)
IGNORED_HTML_CLASSES = {
    "endringsinfo",
    "historikk",
    "fotnote",
    "toolbar",
    "innhold",
    "nav",
    "metadata",
}

# Regex to detect list prefixes: e.g. "a)", "a.", "(a)", "1)", "1.", "(1)", "–", "-"
_PREFIX_PATTERN = re.compile(r"^(\(?[0-9a-zA-Z]{1,3}\)|\b[0-9a-zA-Z]{1,3}\.|\b[0-9a-zA-Z]{1,3}\)|[–\-])\s*")


def _clean_text(text: str) -> str:
    """Collapses consecutive whitespace and trims leading/trailing spaces."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


def parse_legal_blocks(html_content: str) -> List[LegalBlock]:
    if not html_content or not html_content.strip():
        return []

    soup = BeautifulSoup(html_content, "html.parser")

    # Remove script, style, and known non-substantive classes
    for tag in soup(["script", "style"]):
        tag.decompose()

    for cls_name in IGNORED_HTML_CLASSES:
        for tag in soup.find_all(class_=cls_name):
            tag.decompose()

    blocks: List[LegalBlock] = []
    order_idx = 0

    # Look for top-level structural containers
    top_elements = soup.find_all(["article", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"], recursive=False)
    
    # If no top-level matched, examine body/root direct children
    if not top_elements:
        root = soup.body if soup.body else soup
        top_elements = [child for child in root.children if isinstance(child, Tag)]

    # Fallback if structure is flat text without standard container tags
    if not top_elements:
        text = _clean_text(soup.get_text(separator=" ", strip=True))
        if text:
            blocks.append(LegalBlock(block_type="TEXT", text=text, prefix=None, order=0))
        return blocks

    for elem in top_elements:
        elem_classes = elem.get("class", [])
        if isinstance(elem_classes, str):
            elem_classes = [elem_classes]

        tag_name = elem.name.lower()

        # 1. HEADING
        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6") or "heading" in elem_classes or "title" in elem_classes:
            h_text = _clean_text(elem.get_text(separator=" ", strip=True))
            if h_text:
                blocks.append(LegalBlock(block_type="HEADING", text=h_text, prefix=None, order=order_idx))
                order_idx += 1
            continue

        # 2. LIST (Direct top-level ul/ol)
        if tag_name in ("ul", "ol"):
            for li in elem.find_all("li", recursive=False):
                li_text, prefix = _extract_list_item(li)
                if li_text:
                    blocks.append(LegalBlock(block_type="LIST_ITEM", text=li_text, prefix=prefix, order=order_idx))
                    order_idx += 1
            continue

        # 3. LEGAL PARAGRAPH (LEDD) / ARTICLE / P
        # Single-pass: extract text before any nested list, then extract list items separately
        if "legalp" in [c.lower() for c in elem_classes] or tag_name in ("article", "p", "div"):
            ledd_blocks = _extract_ledd_with_nested_lists(elem, order_start=order_idx)
            for b in ledd_blocks:
                blocks.append(b)
                order_idx += 1
            continue

        # 4. Fallback element
        f_text = _clean_text(elem.get_text(separator=" ", strip=True))
        if f_text:
            blocks.append(LegalBlock(block_type="TEXT", text=f_text, prefix=None, order=order_idx))
            order_idx += 1

    return blocks


def _extract_ledd_with_nested_lists(elem: Tag, order_start: int) -> List[LegalBlock]:
    blocks: List[LegalBlock] = []
    current_order = order_start

    # Separate non-list text from list elements
    # We walk direct children of elem
    lead_text_parts: List[str] = []

    for child in elem.children:
        if isinstance(child, NavigableString):
            cleaned = _clean_text(str(child))
            if cleaned:
                lead_text_parts.append(cleaned)
        elif isinstance(child, Tag):
            child_name = child.name.lower()
            if child_name in ("ul", "ol"):
                # First flush any accumulated lead text as a LEDD
                if lead_text_parts:
                    ledd_text = " ".join(lead_text_parts).strip()
                    if ledd_text:
                        blocks.append(LegalBlock(block_type="LEDD", text=ledd_text, prefix=None, order=current_order))
                        current_order += 1
                    lead_text_parts = []

                # Now extract list items
                for li in child.find_all("li", recursive=False):
                    li_text, prefix = _extract_list_item(li)
                    if li_text:
                        blocks.append(LegalBlock(block_type="LIST_ITEM", text=li_text, prefix=prefix, order=current_order))
                        current_order += 1
            else:
                # Other inline or child tags (span, em, a, etc.)
                child_text = _clean_text(child.get_text(separator=" ", strip=True))
                if child_text:
                    lead_text_parts.append(child_text)

    # Flush any remaining text as LEDD / TEXT
    if lead_text_parts:
        ledd_text = " ".join(lead_text_parts).strip()
        if ledd_text:
            blocks.append(LegalBlock(block_type="LEDD", text=ledd_text, prefix=None, order=current_order))

    return blocks
def _extract_list_item(li: Tag) -> tuple[str, Optional[str]]:
    raw_text = _clean_text(li.get_text(separator=" ", strip=True))
    if not raw_text:
        return "", None

    match = _PREFIX_PATTERN.match(raw_text)
    if match:
        prefix = match.group(1).strip()
        return raw_text, prefix

    return raw_text, None
