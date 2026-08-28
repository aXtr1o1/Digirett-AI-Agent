from __future__ import annotations

from ingestion.adapters.legal_html_parser import parse_legal_blocks
from ingestion.adapters.law_section_adapter import LawSectionAdapter
from ingestion.adapters.regulation_section_adapter import RegulationSectionAdapter

__all__ = [
    "parse_legal_blocks",
    "LawSectionAdapter",
    "RegulationSectionAdapter",
]
