import logging
from pathlib import Path
from typing import List, Dict
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def _clean_text(text: str) -> str:
    """Normalize whitespace and remove UI garbage"""
    if not text:
        return ""

    # Remove weird UI characters Lovdata injects
    blacklist = [
        "Verktøylinje",
        "Innholdsfortegnelse",
        "Ditt søk ga dessverre ingen treff",
        "Del paragraf",
        "🔗", "➦", "", "", "", "", "", "", "", "⎙", "",
    ]

    for bad in blacklist:
        text = text.replace(bad, "")

    # Normalize whitespace
    text = " ".join(text.split())
    return text.strip()


# -------------------------------------------------
# Core XML parser
# -------------------------------------------------
def parse_lovdata_xml(xml_path: Path) -> Dict:
    """
    Parse a Lovdata XML file into clean text + metadata and save as .txt
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # 1. Metadata Extraction
        meta = root.find("metadata")
        metadata = {
            "file_name": xml_path.name,
            "id": meta.findtext("id", "") if meta is not None else "",
            "type": meta.findtext("type", "") if meta is not None else "",
            "korttittel": meta.findtext("korttittel", "") if meta is not None else "",
            "fulltittel": meta.findtext("fulltittel", "") if meta is not None else "",
            "dato": meta.findtext("dato", "") if meta is not None else "",
            "url": meta.findtext("url", "") if meta is not None else "",
        }

        # 2. Content Extraction
        text_blocks: List[str] = []

        # Loop through all sections in the XML
        for section in root.findall(".//section"):
            title = section.findtext("title", "")
            content = section.findtext("content", "")

            title = _clean_text(title)
            content = _clean_text(content)

            # Skip empty or UI-only noise
            if len(content) < 30:
                continue

            if title:
                text_blocks.append(f"SECTION: {title}")

            text_blocks.append(content)

        full_text = "\n\n".join(text_blocks).strip()

        # 3. Save to Disk (cleaned_text folder)
        if full_text:
            # Ensure path is relative to the project root
            output_dir = Path("data/cleaned_text")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = output_dir / f"{xml_path.stem}.txt"
            output_path.write_text(full_text, encoding="utf-8")
            logger.info(f"💾 Saved cleaned text to: {output_path}")
        else:
            logger.warning(f"⚠️ No usable text extracted from {xml_path.name}")

        return {
            "file_name": xml_path.name,
            "text": full_text,
            "metadata": metadata,
        }

    except Exception as e:
        logger.exception(f"❌ Failed to parse {xml_path.name}: {e}")
        return {}


# -------------------------------------------------
# Public API (used by main pipeline)
# -------------------------------------------------
def process_xml_to_text(
    xml_files: List[Path],
    max_workers: int = 4,
) -> List[Dict]:
    """
    Convert multiple XML files into clean text documents
    """
    documents: List[Dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # map sends each file in xml_files to the parse_lovdata_xml function
        for result in executor.map(parse_lovdata_xml, xml_files):
            if result and result.get("text"):
                documents.append(result)

    logger.info(f"✅ Converted {len(documents)} XML files to clean text")
    return documents