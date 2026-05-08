"""
adapters/lovdata_adapter.py
============================
Adapter for Lovdata XML files (from Supabase or local disk).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.adapters.base_adapter import BaseAdapter
from ingestion.src.processors.text_processor import parse_lovdata_xml

logger = logging.getLogger(__name__)


class LovdataAdapter(BaseAdapter):
    """Lovdata XML Adapter."""

    def get_source_name(self) -> str:
        return "lovdata"

    def fetch(self, input_path: Optional[str] = None) -> Any:
        """
        If input_path is a directory, load XMLs from it.
        Otherwise, a real implementation would fetch from Supabase.
        """
        dir_path = Path(input_path) if input_path else Path(self.config.get("local_data_dir", "."))
        if not dir_path.exists() or not dir_path.is_dir():
            logger.warning("LovdataAdapter: directory %s not found", dir_path)
            return []
            
        xml_files = list(dir_path.rglob("*.xml"))
        logger.info("LovdataAdapter found %s XML files", len(xml_files))
        return xml_files

    def parse(self, raw_data: Any) -> List[Dict[str, Any]]:
        records = []
        if not raw_data or not isinstance(raw_data, list):
            return records
            
        for xml_path in raw_data:
            if not isinstance(xml_path, Path):
                continue
                
            try:
                # Use the existing robust Lovdata parser
                parsed = parse_lovdata_xml(xml_path)
                if not parsed:
                    continue
                    
                meta = parsed.get("metadata", {})
                
                records.append({
                    "file_name": xml_path.name,
                    "title": meta.get("fulltittel") or meta.get("korttittel") or xml_path.stem,
                    "raw_content": xml_path.read_text(encoding="utf-8", errors="ignore"),
                    "content": parsed.get("text", ""),
                    "source_doc_url": parsed.get("document_url") or meta.get("url", ""),
                    "version_date": meta.get("dato", "")
                })
            except Exception as exc:
                logger.error("LovdataAdapter failed to parse %s: %s", xml_path, exc)
                
        return records
