"""
validation/rule_validator.py
=============================
Level 3 of the validation framework: config-driven business rules.
"""

from __future__ import annotations

import logging
import yaml
from pathlib import Path
from typing import Any, Dict, List

from ingestion.validation.validation_models import Severity, ValidationError, ValidationResult

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "validation_rules.yaml"


class RuleValidator:
    """Validates domain-specific business rules."""

    def __init__(self, config_path: Path = _CONFIG_PATH) -> None:
        self.config_path = config_path
        self.business_rules: List[Dict[str, Any]] = []
        self._load_config()

    def _load_config(self) -> None:
        if not self.config_path.exists():
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.business_rules = data.get("business_rules", [])
        except Exception as exc:
            logger.error("Failed to load business rules from %s: %s", self.config_path, exc)

    def _parse_severity(self, value: str) -> Severity:
        value = (value or "").lower()
        if value == "warning": return Severity.WARNING
        if value == "info": return Severity.INFO
        return Severity.CRITICAL

    def validate(self, doc: Any) -> ValidationResult:
        result = ValidationResult(document_id=doc.get("doc_id") or "unknown")

        for rule in self.business_rules:
            rule_name = rule.get("name", "unnamed_rule")
            field_name = rule.get("field")
            if not field_name:
                continue

            val = doc.get(field_name)
            val_str = str(val) if val is not None else ""
            severity = self._parse_severity(rule.get("severity", "critical"))

            # Must Not Contain
            if "must_not_contain" in rule:
                for bad_phrase in rule["must_not_contain"]:
                    if bad_phrase.lower() in val_str.lower():
                        result.add_error(ValidationError(
                            level="rule", field=field_name, rule=rule_name,
                            message=f"Contains forbidden phrase: '{bad_phrase}'",
                            severity=severity,
                        ))

            # Must Contain
            if "must_contain" in rule:
                for phrase in rule["must_contain"]:
                    if phrase.lower() not in val_str.lower():
                        result.add_error(ValidationError(
                            level="rule", field=field_name, rule=rule_name,
                            message=f"Missing required phrase: '{phrase}'",
                            severity=severity,
                        ))
                        
            # Allowed Values (can also be done at field level, but useful here for complex scenarios)
            if "allowed_values" in rule:
                allowed = [str(x) for x in rule["allowed_values"]]
                if val_str not in allowed:
                    result.add_error(ValidationError(
                        level="rule", field=field_name, rule=rule_name,
                        message=f"Value '{val_str}' is not in {allowed}",
                        severity=severity,
                    ))

        return result
