from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Literal


logger = logging.getLogger(__name__)


LEGAL_VALIDATION_KEYS = ("Legal_Validation", "legal_validation")
DOMAIN_NAME_KEYS = ("Domain Name", "domain_name")
CANONICAL_SUBDOMAIN_KEYS = ("Canonical_Subdomain", "canonical_subdomain")
FILE_NAME_KEYS = ("File Name", "file_name")


@dataclass(frozen=True)
class ValidationDecision:
    action: Literal["ingest", "skip"]
    reason: str
    legal_validation: str
    file_name: str
    final_domain: Optional[str] = None
    final_subdomain: Optional[str] = None

    @property
    def should_ingest(self) -> bool:
        return self.action == "ingest"


class ValidationGate:
    """
    DigiRett validated ingestion gate.

    Rules:
    - allow only Legal_Validation == "remap"
    - skip exclude / pending / empty
    - enforce Canonical_Subdomain presence
    - enforce Domain Name presence
    """

    ALLOWED_STATUS = "remap"
    SKIP_STATUSES = {"exclude", "pending"}

    def evaluate(self, row: Mapping[str, Any]) -> ValidationDecision:
        file_name = self._string(self._get_first(row, FILE_NAME_KEYS)) or "<unknown>"

        legal_validation = self._normalize_status(
            self._get_first(row, LEGAL_VALIDATION_KEYS)
        )

        if not legal_validation:
            return self._skip(
                reason="missing_legal_validation",
                legal_validation="",
                file_name=file_name,
            )

        if legal_validation in self.SKIP_STATUSES:
            return self._skip(
                reason=f"status_{legal_validation}",
                legal_validation=legal_validation,
                file_name=file_name,
            )

        if legal_validation != self.ALLOWED_STATUS:
            return self._skip(
                reason=f"unsupported_status_{legal_validation}",
                legal_validation=legal_validation,
                file_name=file_name,
            )

        final_domain = self._string(self._get_first(row, DOMAIN_NAME_KEYS))
        if not final_domain:
            return self._skip(
                reason="missing_domain_name",
                legal_validation=legal_validation,
                file_name=file_name,
            )

        final_subdomain = self._string(
            self._get_first(row, CANONICAL_SUBDOMAIN_KEYS)
        )
        if not final_subdomain:
            return self._skip(
                reason="missing_canonical_subdomain",
                legal_validation=legal_validation,
                file_name=file_name,
            )

        return ValidationDecision(
            action="ingest",
            reason="ok",
            legal_validation=legal_validation,
            file_name=file_name,
            final_domain=final_domain,
            final_subdomain=final_subdomain,
        )

    def extract_final_metadata(self, row: Mapping[str, Any]) -> dict[str, str]:
        """
        Returns canonical metadata only for rows that pass validation.
        Raises ValueError if the row is not ingestable.
        """
        decision = self.evaluate(row)
        if not decision.should_ingest:
            raise ValueError(
                f"Row is not ingestable: file={decision.file_name}, reason={decision.reason}"
            )

        return {
            "domain": decision.final_domain or "",
            "subdomain": decision.final_subdomain or "",
            "legal_validation": decision.legal_validation,
            "file_name": decision.file_name,
        }

    @staticmethod
    def should_ingest(row: Mapping[str, Any]) -> bool:
        return ValidationGate().evaluate(row).should_ingest

    def _skip(
        self,
        *,
        reason: str,
        legal_validation: str,
        file_name: str,
    ) -> ValidationDecision:
        logger.info(
            "Validation skipped | file=%s | status=%s | reason=%s",
            file_name,
            legal_validation or "<empty>",
            reason,
        )
        return ValidationDecision(
            action="skip",
            reason=reason,
            legal_validation=legal_validation,
            file_name=file_name,
        )

    @staticmethod
    def _get_first(row: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in row:
                return row[key]
        return None

    @staticmethod
    def _normalize_status(value: Any) -> str:
        text = ValidationGate._string(value)
        return text.lower() if text else ""

    @staticmethod
    def _string(value: Any) -> str:
        if value is None:
            return ""

        # Handles NaN without importing pandas/numpy.
        try:
            if isinstance(value, float) and value != value:
                return ""
        except Exception:
            pass

        text = str(value).strip()
        return "" if text.lower() in {"", "nan", "none", "null"} else text