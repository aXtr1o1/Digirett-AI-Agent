"""
validation/field_validator.py
==============================
Level 2 of the validation framework: config-driven per-field format checks.
"""

from __future__ import annotations

import logging
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List

from ingestion.validation.validation_models import Severity, ValidationError, ValidationResult

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "validation_rules.yaml"


class FieldValidator:
    """Validates individual field values (length, pattern, allowed choices)."""

    def __init__(self, config_path: Path = _CONFIG_PATH) -> None:
        self.config_path = config_path
        self.rules: Dict[str, Dict[str, Any]] = {}
        self._load_config()

    def _load_config(self) -> None:
        if not self.config_path.exists():
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.rules = data.get("field_rules", {})
        except Exception as exc:
            logger.error("Failed to load field rules from %s: %s", self.config_path, exc)

    def _parse_severity(self, value: str) -> Severity:
        value = (value or "").lower()
        if value == "warning": return Severity.WARNING
        if value == "info": return Severity.INFO
        return Severity.CRITICAL

    def validate(self, doc: Any) -> ValidationResult:
        result = ValidationResult(document_id=doc.get("doc_id") or "unknown")

        for field_name, rules in self.rules.items():
            val = doc.get(field_name)
            val_str = str(val).strip() if val is not None else ""
            severity = self._parse_severity(rules.get("severity", "critical"))

            # If empty and not required, skip format checks
            required = rules.get("required", True)
            if not val_str and not required:
                continue

            # Length checks
            if "min_length" in rules and len(val_str) < rules["min_length"]:
                result.add_error(ValidationError(
                    level="field", field=field_name, rule="min_length",
                    message=f"Length {len(val_str)} < {rules['min_length']}",
                    severity=severity,
                ))
            
            if "max_length" in rules and len(val_str) > rules["max_length"]:
                result.add_error(ValidationError(
                    level="field", field=field_name, rule="max_length",
                    message=f"Length {len(val_str)} > {rules['max_length']}",
                    severity=severity,
                ))

            # Pattern checks
            if "pattern" in rules and val_str:
                try:
                    if not re.match(rules["pattern"], val_str):
                        result.add_error(ValidationError(
                            level="field", field=field_name, rule="pattern",
                            message=f"Does not match pattern: {rules['pattern']}",
                            severity=severity,
                        ))
                except re.error:
                    logger.warning("Invalid regex pattern for %s: %s", field_name, rules["pattern"])

            # Allowed values
            if "allowed_values" in rules:
                allowed = [str(x) for x in rules["allowed_values"]]
                if val_str not in allowed:
                    result.add_error(ValidationError(
                        level="field", field=field_name, rule="allowed_values",
                        message=f"Value '{val_str}' not in allowed list",
                        severity=severity,
                    ))

        return result
