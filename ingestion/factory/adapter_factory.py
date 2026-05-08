"""
factory/adapter_factory.py
===========================
Dynamically instantiates adapters based on source_config.yaml.
"""

from __future__ import annotations

import logging
import yaml
from pathlib import Path
from typing import Dict, List, Optional

from ingestion.adapters.base_adapter import BaseAdapter
from ingestion.adapters.lovdata_adapter import LovdataAdapter
from ingestion.adapters.xapi_adapter import XAPIAdapter
from ingestion.adapters.file_adapter import FileAdapter
from ingestion.adapters.generic_api_adapter import GenericApiAdapter

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "source_config.yaml"


class AdapterFactory:
    """Registry and factory for source adapters."""

    def __init__(self, config_path: Path = _CONFIG_PATH) -> None:
        self.config_path = config_path
        self.sources_config: Dict[str, dict] = {}
        self._load_config()

        # Hardcoded registry for now. Could be dynamic using importlib.
        self._registry = {
            "lovdata": LovdataAdapter,
            "xapi": XAPIAdapter,
            "file": FileAdapter,
            "generic_api": GenericApiAdapter,
        }

    def _load_config(self) -> None:
        if not self.config_path.exists():
            logger.warning("Source config missing at %s", self.config_path)
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.sources_config = data.get("sources", {})
        except Exception as exc:
            logger.error("Failed to load source config: %s", exc)

    def create(self, source_name: str) -> BaseAdapter:
        """Instantiate a specific adapter by name."""
        config = self.sources_config.get(source_name)
        if not config:
            raise ValueError(f"Source '{source_name}' not found in config.")

        adapter_type = config.get("adapter")
        adapter_class = self._registry.get(adapter_type)

        if not adapter_class:
            logger.warning("Adapter type '%s' unknown, falling back to generic_api", adapter_type)
            adapter_class = GenericApiAdapter

        return adapter_class(config)

    def create_all_enabled(self) -> List[BaseAdapter]:
        """Instantiate all adapters marked as enabled in config."""
        adapters = []
        for src_name, config in self.sources_config.items():
            if config.get("enabled") is True:
                try:
                    adapters.append(self.create(src_name))
                except Exception as exc:
                    logger.error("Failed to create adapter for %s: %s", src_name, exc)
        return adapters
