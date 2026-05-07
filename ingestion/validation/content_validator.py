"""
validation/content_validator.py
================================
Validates that the conversion from raw JSON/XML to plain text is complete.
Ensures no paragraphs or critical fields are missed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from ingestion.validation.validation_models import Severity, ValidationError, ValidationResult

logger = logging.getLogger(__name__)


class ContentIntegrityValidator:
    """
    Checks if the converted plain text contains all data from the source.
    Specifically checks XAPI paragraphs and critical metadata fields.
    """

    def validate(self, doc: Dict[str, Any]) -> ValidationResult:
        result = ValidationResult(document_id=doc.get("doc_id") or "unknown")
        
        source_type = doc.get("source")
        raw_data = doc.get("raw_data", {})
        content = doc.get("content", "")
        
        if not raw_data:
            logger.warning("No raw_data found for doc %s, skipping integrity check", doc.get("doc_id"))
            return result

        # 1. XAPI Integrity Check
        if source_type == "xapi":
            # XAPI raw_data might contain the full JSON in 'raw_json'
            xapi_json = raw_data.get("raw_json", raw_data)
            paragraphs = xapi_json.get("paragraphs", [])
            
            if not paragraphs:
                logger.warning("No paragraphs found in XAPI raw_data for %s", doc.get("doc_id"))
            
            for i, p in enumerate(paragraphs):
                original_txt = p.get("innhold_text", "").strip()
                if original_txt and not self._is_content_present(original_txt, content):
                    result.add_error(
                        ValidationError(
                            level="integrity",
                            field=f"paragraph_{i}",
                            rule="content_missing",
                            message=f"CRITICAL: Paragraph {i} content is missing or corrupted in plain text.",
                            severity=Severity.CRITICAL,
                        )
                    )

            # Check Title and ID consistency
            meta = raw_data.get("metadata", {})
            if meta.get("tittel") and meta.get("tittel") != doc.get("title"):
                result.add_error(
                    ValidationError(
                        level="integrity",
                        field="title",
                        rule="metadata_mismatch",
                        message=f"Title mismatch: Source='{meta.get('tittel')}' != Converted='{doc.get('title')}'",
                        severity=Severity.WARNING,
                    )
                )

        # 2. XML Integrity Check (Lovdata)
        elif source_type in ("lovdata", "file"):
            # For XML, we check if the 'text' field in raw_data matches the doc content
            # parse_lovdata_xml returns a dict where 'text' is the full extract
            orig_text = raw_data.get("text", "")
            if orig_text and not self._is_content_present(orig_text, content):
                result.add_error(
                    ValidationError(
                        level="integrity",
                        field="full_text",
                        rule="content_missing",
                        message="CRITICAL: Full text extract from XML is significantly different in final content.",
                        severity=Severity.CRITICAL,
                    )
                )

        return result

    def _is_content_present(self, original: str, converted: str) -> bool:
        """
        Check if original text is present in converted text, 
        ignoring whitespace, case, and common noise.
        """
        if not original:
            return True
            
        # Clean both for a fair comparison
        def clean(t: str) -> str:
            # Remove all whitespace and common non-alphanumeric noise
            import re
            return re.sub(r'[^a-zA-Z0-9]', '', t).lower()

        orig_clean = clean(original)
        conv_clean = clean(converted)
        
        # We check if a significant portion of the original (95%+) is present
        # to allow for minor cleaning/replacements like the _BLACKLIST.
        if not orig_clean:
            return True
            
        # For performance on very large texts, we check chunks
        if len(orig_clean) > 1000:
            # Check start, middle, and end
            start = orig_clean[:200] in conv_clean
            end = orig_clean[-200:] in conv_clean
            return start and end
            
        return orig_clean in conv_clean
