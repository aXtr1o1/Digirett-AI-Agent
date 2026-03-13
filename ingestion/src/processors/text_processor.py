### This code is the main Lovdata collector that fetches XML files from the LOVDATA_API_URL, processes them into clean text, and prepares them for embedding and storage.
# ----------------------------------------------------------
# import os
# from lxml import etree as ET
# from ingestion.src.config import CLEAN_TEXT_DIR
# from concurrent.futures import ProcessPoolExecutor, as_completed
# from tqdm import tqdm
# import logging

# # Configure logging
# logger = logging.getLogger(__name__)

# def extract_all_metadata(root):
#     """
#     Dynamically extracts ALL metadata from XML header.
#     Finds all dt/dd pairs and preserves their exact labels.
#     """
#     metadata = []  # Use list to preserve order
    
#     # Find document header
#     header = root.find(".//header[@class='documentHeader']")
#     if header is None:
#         header = root.find(".//header")
#     if header is None:
#         header = root
    
#     # Find all dt elements (field labels)
#     dt_elements = header.findall(".//dt")
    
#     for dt in dt_elements:
#         # Get label text (what's displayed to user)
#         label_text = "".join(dt.itertext()).strip()
#         if not label_text:
#             continue
        
#         # Find corresponding dd element (the value)
#         dd = None
#         next_sibling = dt.getnext()
#         if next_sibling is not None and next_sibling.tag == 'dd':
#             dd = next_sibling
        
#         if dd is not None:
#             # Check for list structure (ul/li)
#             ul = dd.find('.//ul')
#             if ul is not None:
#                 items = []
#                 for li in ul.findall('.//li'):
#                     # Get all text including nested elements
#                     text = "".join(li.itertext()).strip()
#                     if text:
#                         items.append(text)
#                 if items:
#                     metadata.append((label_text, items))
#             else:
#                 # Regular text content - get all text including nested elements
#                 text = "".join(dd.itertext()).strip()
#                 if text:
#                     metadata.append((label_text, text))
    
#     return metadata


# def find_year_in_text(text):
#     """
#     Searches for any 4-digit year (1600-2099) in text.
#     """
#     if not text:
#         return None
    
#     words = text.replace('-', ' ').replace('/', ' ').replace('.', ' ').replace(':', ' ').split()
#     for word in words:
#         # Remove any trailing/leading punctuation
#         clean_word = word.strip('.,;:!?()[]{}"\'-')
#         if clean_word.isdigit() and len(clean_word) == 4:
#             year_int = int(clean_word)
#             if 1600 <= year_int <= 2099:
#                 return clean_word
#     return None


# def extract_year(metadata):
#     """
#     Extracts year from metadata list.
#     """
#     # Search through all metadata values
#     for label, value in metadata:
#         if isinstance(value, list):
#             for item in value:
#                 year = find_year_in_text(item)
#                 if year:
#                     return year
#         else:
#             year = find_year_in_text(value)
#             if year:
#                 return year
#     return None


# def format_metadata_header(metadata, year):
#     """
#     Formats metadata exactly as shown in samples.
#     Field Name
#         - Value
#     """
#     lines = []
    
#     # Add all metadata fields
#     for label, value in metadata:
#         lines.append(label)
        
#         if isinstance(value, list):
#             # Multi-value field
#             for item in value:
#                 lines.append(f"    - {item}")
#         else:
#             # Single value
#             lines.append(f"    - {value}")
    
#     # Add year if found
#     if year:
#         lines.append(f"YEAR: {year}")
    
#     # Add separator
#     lines.append("-" * 40)
    
#     return "\n".join(lines)


# def extract_document_body(main_body):
#     """
#     Extracts document content with full structure preservation.
#     Handles all heading levels, paragraphs, sections, and lists.
#     """
#     lines = []
#     seen_text = set()  # Avoid duplicates
    
#     # Get main title (h1)
#     h1 = main_body.find(".//h1")
#     if h1 is not None:
#         title = "".join(h1.itertext()).strip()
#         if title and title not in seen_text:
#             lines.append(title)
#             seen_text.add(title)
    
#     # Process all elements in order
#     for element in main_body.iter():
#         tag = element.tag
#         classes = element.get('class', '')
        
#         # Skip if this element is inside another we'll process
#         if element.getparent() is not None:
#             parent_tag = element.getparent().tag
#             parent_class = element.getparent().get('class', '')
#             # Skip text inside article/p elements that will be processed as whole
#             if parent_tag in ['article', 'p'] and tag in ['span', 'strong', 'em']:
#                 continue
        
#         # All heading levels (h1-h6)
#         if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
#             header_text = "".join(element.itertext()).strip()
#             if header_text and header_text not in seen_text:
#                 # h1 already added above, skip duplicate
#                 if tag == 'h1' and header_text in seen_text:
#                     continue
#                 lines.append(f"\n{header_text}")
#                 seen_text.add(header_text)
        
#         # Paragraphs with legal/default classes
#         elif tag == 'article' and any(cls in classes for cls in ['legalP', 'defaultP', 'numberedLegalP', 'futureLegalArticle']):
#             # Get all text from this article
#             para_text = "".join(element.itertext()).strip()
            
#             if para_text and para_text not in seen_text:
#                 # Check for numbering
#                 numerator = element.get('data-numerator', '').strip()
                
#                 if numerator:
#                     lines.append(f"\n({numerator}) {para_text}")
#                 else:
#                     lines.append(f"\n{para_text}")
                
#                 seen_text.add(para_text)
        
#         # Regular paragraphs
#         elif tag == 'p' and any(cls in classes for cls in ['legalP', 'defaultP']):
#             para_text = "".join(element.itertext()).strip()
#             if para_text and para_text not in seen_text:
#                 lines.append(f"\n{para_text}")
#                 seen_text.add(para_text)
        
#         # List items with identifiers
#         elif tag == 'li':
#             # Skip if inside table of contents
#             parent = element.getparent()
#             while parent is not None:
#                 if parent.get('class') == 'table-of-contents':
#                     break
#                 parent = parent.getparent()
#             else:
#                 # Not in TOC, process it
#                 identifier = element.get('data-li-identifier', '').strip()
#                 if not identifier:
#                     identifier = element.get('data-name', '').strip()
                
#                 item_text = "".join(element.itertext()).strip()
                
#                 # Remove identifier from text if already at start
#                 if identifier and item_text.startswith(identifier):
#                     item_text = item_text[len(identifier):].strip()
                
#                 if item_text and item_text not in seen_text:
#                     if identifier:
#                         lines.append(f"  {identifier} {item_text}")
#                     else:
#                         lines.append(f"  {item_text}")
#                     seen_text.add(item_text)
    
#     return lines


# def xml_to_structured_text(xml_path, file_name):
#     """
#     Converts ANY Norwegian legal XML to structured text format.
#     Fully dynamic - adapts to any structure automatically.
#     Handles 10,000+ files with different formats.
#     """
#     try:
#         tree = ET.parse(xml_path)
#         root = tree.getroot()
#     except ET.ParseError as e:
#         logging.error(f"XML Parse Error [{file_name}]: {e}")
#         return ""
#     except FileNotFoundError:
#         logging.error(f"File Not Found [{file_name}]: {xml_path}")
#         return ""
#     except Exception as e:
#         logging.error(f"Error parsing [{file_name}]: {e}")
#         return ""
    
#     try:
#         # Extract all metadata dynamically
#         metadata = extract_all_metadata(root)
        
#         # Find year from metadata
#         year = extract_year(metadata)
        
#         # Format metadata header
#         header = format_metadata_header(metadata, year)

#         def extract_lovdata_url(root):
#             """
#             Extract Lovdata document URL from XML.
#             """
#             main_tag = root.find(".//main")

#             if main_tag is not None:
#                 lovdata_path = main_tag.attrib.get("data-lovdata-URL")

#                 if lovdata_path:
#                     return f"https://lovdata.no/dokument/{lovdata_path}"

#             return None

        
#         # Extract document body
#         main_body = root.find(".//main")
#         if main_body is None:
#             main_body = root.find(".//body")
#         if main_body is None:
#             main_body = root
        
#         content_lines = extract_document_body(main_body)
        
#         # Combine header + content
#         full_text = header + "\n" + "\n".join(content_lines).strip()
        
#         document_url = extract_lovdata_url(root)

#         return {
#             "text": full_text,
#             "document_url": document_url
#         }

        
#     except Exception as e:
#         logging.error(f"Content extraction error [{file_name}]: {e}")
#         import traceback
#         logging.error(traceback.format_exc())
#         return ""


# def process_single_file(xml_path):
#     """
#     Processes one XML file atomically.
#     Returns processing status.
#     """
#     if not isinstance(xml_path, (str, os.PathLike)):
#         raise TypeError(f"Expected xml_path to be str or Path, got {type(xml_path)}")

#     base_name = os.path.basename(xml_path)
#     txt_name = base_name.replace(".xml", ".txt")

#     result = xml_to_structured_text(xml_path, txt_name)

#     if not result:
#         return {'status': 'failed', 'file': txt_name}

#     text_content = result["text"]
#     document_url = result.get("document_url")


#     if not text_content:
#         return {'status': 'failed', 'file': txt_name}

#     output_path = os.path.join(CLEAN_TEXT_DIR, txt_name)
#     try:
#         with open(output_path, "w", encoding="utf-8") as f:
#             f.write(text_content)
#     except Exception as e:
#         logging.error(f"File write error [{txt_name}]: {e}")
#         return {'status': 'failed', 'file': txt_name}

#     has_year = "YEAR:" in text_content

#     return {
#     'status': 'success',
#     'file': txt_name,
#     'has_year': has_year,
#     'document_url': document_url
#     }



# def process_xml_to_text(xml_files, max_workers=4):
#     """
#     Batch processes XML files to structured text format.
#     Optimized for 10,000+ files with different structures.
    
#     Args:
#         xml_files: List of XML file paths
#         max_workers: Number of parallel workers (default: 4)
    
#     Returns:
#         List of document dictionaries with 'file_name' and 'text' keys
#     """
#     os.makedirs(CLEAN_TEXT_DIR, exist_ok=True)
    
#     documents = []
#     stats = {
#         'total': len(xml_files),
#         'success': 0,
#         'failed': 0,
#         'no_year': 0,
#         'failed_files': []
#     }
    
#     logging.info(f"Starting batch processing: {stats['total']} files")
    
#     # Parallel processing with progress bar
#     with ProcessPoolExecutor(max_workers=max_workers) as executor:
#         futures = {executor.submit(process_single_file, path): path for path in xml_files}
        
#         with tqdm(total=stats['total'], desc="Processing XML files", unit="file") as pbar:
#             for future in as_completed(futures):
#                 result = future.result()
                
#                 if result['status'] == 'success':
#                     stats['success'] += 1
                    
#                     # Read the saved file content
#                     txt_path = os.path.join(CLEAN_TEXT_DIR, result['file'])
#                     try:
#                         with open(txt_path, 'r', encoding='utf-8') as f:
#                             text_content = f.read()
                        
#                         documents.append({
#                             'file_name': result['file'],
#                             'text': text_content,
#                             'document_url': result.get("document_url")
#                         })

#                     except Exception as e:
#                         logging.error(f"Error reading saved file [{result['file']}]: {e}")
                    
#                     if not result['has_year']:
#                         stats['no_year'] += 1
#                 else:
#                     stats['failed'] += 1
#                     stats['failed_files'].append(result['file'])
                
#                 pbar.update(1)
    
#     # Print summary
#     print(f"\n{'='*60}")
#     print(f"BATCH PROCESSING COMPLETED")
#     print(f"{'='*60}")
#     print(f"  Total files:         {stats['total']}")
#     print(f"  ✓ Successful:        {stats['success']} ({stats['success']/stats['total']*100:.1f}%)")
#     print(f"  ✗ Failed:            {stats['failed']} ({stats['failed']/stats['total']*100:.1f}%)")
#     print(f"  ⚠ Without year:      {stats['no_year']} ({stats['no_year']/max(stats['success'],1)*100:.1f}% of successful)")
#     print(f"{'='*60}")
    
#     # Show failed files
#     if stats['failed_files']:
#         print(f"\n⚠ Failed files ({len(stats['failed_files'])}):")
#         for i, fname in enumerate(stats['failed_files'][:10], 1):
#             print(f"  {i}. {fname}")
#         if len(stats['failed_files']) > 10:
#             print(f"  ... and {len(stats['failed_files']) - 10} more")
#         print(f"\nCheck 'xml_processing.log' for details\n")
    
#     logging.info(f"Batch processing completed: {stats['success']}/{stats['total']} successful")
#     logging.info(f"Returning {len(documents)} documents for further processing")
    
#     return documents
#----------------------------------------------------------

"""
processors/text_processor.py
==============================
Parses raw Lovdata XML files into clean plain text documents ready for chunking.

Text extraction priority:
  1. <full_text>  — raw line-by-line page text; preserves § numbers, ledd (1)(2),
                    chapter headings exactly as on lovdata.no. Best for chunker.
  2. <paragraphs> — individual <paragraph> elements joined in order.
  3. <sections>   — HTML layout <div> blocks (last resort; loses § structure).

Why <full_text> first?
  The scraper maps HTML <div> containers to <section> elements. A single
  <div class="docMain"> wraps the entire act, so <section><content> is one
  unstructured blob — the chunker cannot find § markers and collapses
  everything into "Innledning" chunks. <full_text> is scraped with
  get_text(separator=newline) which naturally preserves § line boundaries.

Scraper error files (status=error or <e> tag) are skipped cleanly.
"""

import logging
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

_BLACKLIST = [
    "Verktøylinje",
    "Innholdsfortegnelse",
    "Ditt søk ga dessverre ingen treff",
    "Del paragraf",
    "\U0001f517", "➦", "\ue000", "\ue001", "\ue002",
    "\ue003", "\ue004", "\ue005", "\ue006", "⎙", "\ue007",
]


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
    Produced by BeautifulSoup get_text(separator='\\n') — preserves § markers.
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


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_lovdata_xml(xml_path: Path) -> Dict:
    """
    Parse one Lovdata XML file into clean text + metadata dict.
    Returns {} on error or for scraper-error files.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

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
                f"Skipping scraper-error file: {xml_path.name} | "
                f"url={metadata['url']} | reason={reason}"
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
            logger.warning(f"No usable text in any source: {xml_path.name}")
            return {}

        logger.info(
            f"Parsed {xml_path.name} | source={source} | "
            f"chars={len(full_text):,} | "
            f"lines={full_text.count(chr(10)) + 1} | "
            f"korttittel={metadata['korttittel']!r}"
        )

        return {
            "file_name":    xml_path.name,
            "text":         full_text,
            "metadata":     metadata,
            "document_url": metadata.get("url", "").strip(),
        }

    except Exception as exc:
        logger.exception(f"Failed to parse {xml_path.name}: {exc}")
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
        f"Converted {len(documents)}/{len(xml_files)} XML file(s) to clean text"
    )
    return documents