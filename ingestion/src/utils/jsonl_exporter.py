from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.src.config import NORMALIZED_DIR

logger = logging.getLogger(__name__)


class FormatNormaliser:
    """Exports normalized data collections to JSONL format."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or NORMALIZED_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_jsonl(self, filename: str, records: List[Dict[str, Any]]) -> Path:
        target_path = self.output_dir / filename
        with open(target_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        logger.info("Normalized JSONL written: %s (%d records)", target_path, len(records))
        return target_path

    def export_all(
        self,
        laws: List[Dict[str, Any]],
        paragraphs: List[Dict[str, Any]],
        regulations: List[Dict[str, Any]],
        provisions: List[Dict[str, Any]],
        chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Path]:
        res = {
            "laws": self.write_jsonl("laws.jsonl", laws),
            "law_paragraphs": self.write_jsonl("law_paragraphs.jsonl", paragraphs),
            "regulations": self.write_jsonl("regulations.jsonl", regulations),
            "regulation_provisions": self.write_jsonl("regulation_provisions.jsonl", provisions),
        }
        if chunks is not None:
            res["chunks"] = self.write_jsonl("chunks.jsonl", chunks)
        return res
