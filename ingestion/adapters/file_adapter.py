"""
adapters/file_adapter.py
=========================
Adapter for reading local files (TXT, XML).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class FileAdapter(BaseAdapter):
    """Adapter for local file uploads."""

    def get_source_name(self) -> str:
        return "file_upload"

    def fetch(self, input_path: Optional[str] = None) -> Any:
        # Use provided input path or fallback to config
        watch_dir_str = input_path or self.config.get("watch_dir", "./data/uploads")
        watch_dir = Path(watch_dir_str)
        
        if not watch_dir.exists() or not watch_dir.is_dir():
            logger.warning("FileAdapter: watch directory %s does not exist", watch_dir)
            return []

        allowed_formats = self.config.get("formats", ["txt"])
        files = []
        
        for fmt in allowed_formats:
            files.extend(list(watch_dir.rglob(f"*.{fmt}")))
            
        logger.info("FileAdapter found %s files in %s", len(files), watch_dir)
        return files

    def parse(self, raw_data: Any) -> List[Dict[str, Any]]:
        records = []
        if not raw_data or not isinstance(raw_data, list):
            return records
            
        for file_path in raw_data:
            if not isinstance(file_path, Path):
                continue
                
            try:
                content = file_path.read_text(encoding="utf-8")
                records.append({
                    "file_name": file_path.name,
                    "title": file_path.stem,
                    "raw_content": content,
                    "content": content,  # Minimal normalisation for generic files
                    "source_url": f"file://{file_path.absolute()}"
                })
            except Exception as exc:
                logger.error("FileAdapter failed to read %s: %s", file_path, exc)
                
        return records
