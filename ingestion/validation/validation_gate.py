"""
validation/validation_gate.py
==============================
Orchestrates the multi-level validation strategy for the new layered pipeline.
Note: Named PipelineValidationGate to avoid clashing with the existing ValidationGate.
"""

from __future__ import annotations

import logging
from typing import Optional, Any

from ingestion.validation.field_validator import FieldValidator
from ingestion.validation.rule_validator import RuleValidator
from ingestion.validation.content_validator import ContentIntegrityValidator
from ingestion.validation.validation_models import ValidationResult

logger = logging.getLogger(__name__)


class PipelineValidationGate:
    """
    Runs all validators and decides the final outcome.
    Mutates the document in-place with status and errors.
    """

    def __init__(self) -> None:
        self.field_validator = FieldValidator()
        self.rule_validator = RuleValidator()
        self.integrity_validator = ContentIntegrityValidator()

    def evaluate(self, doc: Any) -> Any:
        """
        Run all validation levels.
        Updates `validation_status` and `validation_errors` on the doc.
        """
        result = ValidationResult(document_id=doc.get("doc_id") or "unknown")

        # 1. Fields
        res_field = self.field_validator.validate(doc)
        result.merge(res_field)

        # 2. Rules
        res_rule = self.rule_validator.validate(doc)
        result.merge(res_rule)

        # 3. Content Integrity (JSON to Text comparison)
        res_integrity = self.integrity_validator.validate(doc)
        result.merge(res_integrity)

        # Determine outcome
        result.compute_outcome()

        # Update document
        doc["validation_status"] = result.outcome.value
        doc["validation_errors"] = [str(e) for e in result.errors]

        status_icon = "[OK]" if result.passed else ("[WARN]" if doc["validation_status"] == "PARTIAL" else "[FAIL]")
        logger.info(
            "  %s VALIDATE | doc=%-24s | src=%-12s | status=%-8s | title=%s",
            status_icon,
            doc.get("doc_id"),
            doc.get("source") or "?",
            doc["validation_status"],
            (doc.get("title") or "<no title>")[:55],
        )

        if not result.passed:
            for err in result.critical_errors:
                logger.warning("      +- ERROR: %s", err)

        return doc
