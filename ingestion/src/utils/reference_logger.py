import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

def log_for_reference(
    file_name: str,
    raw_content: Any,
    text_content: str,
    is_xml: bool = False
):
    """
    Save raw files and normalized text to logs for reference.
    Limits the number of saved files to 5.
    
    Args:
        file_name: Name of the file (e.g., 'lov-2021-06-18-99')
        raw_content: The raw content (dict for JSON, string for XML)
        text_content: The normalized plain text content
        is_xml: True if the raw content is XML
    """
    # Use absolute paths relative to the workspace root if possible, 
    # but here we use relative paths assuming we're in the ingestion context.
    # The runner usually runs from the 'ingestion' directory or project root.
    
    # Try to find the 'ingestion' directory
    base_dir = Path("ingestion")
    if not base_dir.exists():
        # Fallback to current directory if 'ingestion' is not found
        base_dir = Path(".")
        
    log_dir = base_dir / "logs"
    raw_dir = log_dir / "raw_files"
    text_dir = log_dir / "text"
    
    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
        text_dir.mkdir(parents=True, exist_ok=True)
        
        # Check limit: only 5 files total in raw_files
        # We count both .json and .xml
        existing_raw = list(raw_dir.glob("*.json")) + list(raw_dir.glob("*.xml"))
        
        if len(existing_raw) >= 5:
            # Check if this specific file already exists (maybe we're overwriting)
            stem = Path(file_name).stem
            exists = any(f.stem == stem for f in existing_raw)
            if not exists:
                return

        file_stem = Path(file_name).stem
        
        # 1. Save raw file
        ext = ".xml" if is_xml else ".json"
        raw_path = raw_dir / f"{file_stem}{ext}"
        
        if is_xml:
            if isinstance(raw_content, bytes):
                raw_path.write_bytes(raw_content)
            else:
                raw_path.write_text(str(raw_content), encoding="utf-8")
        else:
            if isinstance(raw_content, (dict, list)):
                raw_path.write_text(json.dumps(raw_content, ensure_ascii=False, indent=2), encoding="utf-8")
            elif isinstance(raw_content, bytes):
                raw_path.write_bytes(raw_content)
            else:
                raw_path.write_text(str(raw_content), encoding="utf-8")
                
        # 2. Save plain text log
        text_path = text_dir / f"{file_stem}.txt"
        text_path.write_text(text_content, encoding="utf-8")
        
        logger.info(f"Reference log saved: {file_stem}")
        
    except Exception as e:
        logger.error(f"Failed to save reference log for {file_name}: {e}")
