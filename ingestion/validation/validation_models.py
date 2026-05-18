"""
validation/validation_models.py
================================
Shared types for the multi-level validation framework.

Used by: schema_validator, field_validator, rule_validator, validation_gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class ValidationOutcome(Enum):
    """Final outcome for a document's validation."""

    PASS = "PASS"           # All checks passed
    FAIL = "FAIL"           # Critical failure — document should be skipped
    PARTIAL = "PARTIAL"     # Non-critical issues — proceed with warnings
    SKIP = "SKIP"           # Not applicable / intentionally skipped


class Severity(Enum):
    """How serious a single validation error is."""

    CRITICAL = "critical"   # Blocks ingestion
    WARNING = "warning"     # Logged but does not block
    INFO = "info"           # Informational only


@dataclass(frozen=True)
class ValidationError:
    """
    One specific validation failure.

    Attributes:
        level:    Which validator produced it ("schema", "field", "rule").
        field:    The document field that failed (e.g. "title", "content").
        rule:     Short machine-readable rule name (e.g. "min_length").
        message:  Human-readable description.
        severity: How serious this error is.
    """

    level: str
    field: str
    rule: str
    message: str
    severity: Severity = Severity.CRITICAL

    def __str__(self) -> str:
        return f"[{self.severity.value}] {self.level}.{self.field}: {self.message} (rule={self.rule})"


@dataclass
class ValidationResult:
    """
    Aggregated result of running all validators on a single document.

    The ``outcome`` is computed by ``PipelineValidationGate`` after all
    three validator levels have contributed their errors.
    """

    outcome: ValidationOutcome = ValidationOutcome.PASS
    errors: List[ValidationError] = field(default_factory=list)
    document_id: str = ""

    # ── Helpers ─────────────────────────────────────────────────────────

    @property
    def passed(self) -> bool:
        return self.outcome in (ValidationOutcome.PASS, ValidationOutcome.PARTIAL)

    @property
    def critical_errors(self) -> List[ValidationError]:
        return [e for e in self.errors if e.severity == Severity.CRITICAL]

    @property
    def warnings(self) -> List[ValidationError]:
        return [e for e in self.errors if e.severity == Severity.WARNING]

    def add_error(self, error: ValidationError) -> None:
        self.errors.append(error)

    def merge(self, other: "ValidationResult") -> None:
        """Merge errors from another result into this one."""
        self.errors.extend(other.errors)

    def compute_outcome(self) -> None:
        """
        Set ``self.outcome`` based on accumulated errors.

        Rules:
            - Any CRITICAL error  → FAIL
            - Only WARNING errors → PARTIAL
            - No errors           → PASS
        """
        if self.critical_errors:
            self.outcome = ValidationOutcome.FAIL
        elif self.warnings:
            self.outcome = ValidationOutcome.PARTIAL
        else:
            self.outcome = ValidationOutcome.PASS

    def summary(self) -> str:
        """One-line summary for logging."""
        c = len(self.critical_errors)
        w = len(self.warnings)
        return f"{self.outcome.value} | critical={c} warnings={w} | doc={self.document_id[:16]}"
