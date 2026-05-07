"""
adapters/base_adapter.py
========================
Abstract base class for all data adapters.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """
    Interface for source adapters.
    
    The pipeline calls `run()`, which internally should call
    `fetch()` and `parse()`.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.source_name = self.get_source_name()
        
    @abstractmethod
    def get_source_name(self) -> str:
        """Return the unique identifier for this source (e.g. 'lovdata')."""
        pass

    @abstractmethod
    def fetch(self, input_path: Optional[str] = None) -> Any:
        """
        Fetch raw data from the source (API, database, file system).
        Returns whatever intermediate format makes sense for this adapter.
        """
        pass

    @abstractmethod
    def parse(self, raw_data: Any) -> List[Dict[str, Any]]:
        """
        Parse the fetched data into a list of raw dictionaries.
        These dictionaries will be passed to FormatNormaliser next.
        """
        pass

    def run(self, input_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Standard execution flow: Fetch -> Parse -> Return raw records.
        """
        logger.info("Running adapter: %s", self.source_name)
        try:
            raw_data = self.fetch(input_path=input_path)
            records = self.parse(raw_data)
            logger.info("Adapter %s returned %s records", self.source_name, len(records))
            
            # Ensure every record tags its source
            for r in records:
                r["source_name"] = self.source_name
                
            return records
        except Exception as exc:
            logger.error("Adapter %s failed: %s", self.source_name, exc, exc_info=True)
            return []
