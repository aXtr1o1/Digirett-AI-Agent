from __future__ import annotations

import logging
import re
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

TITLE_ONLY_TOKEN_THRESHOLD = 50
SHORT_TEXT_CHAR_LIMIT = 100
LEGAL_VERBS: frozenset[str] = frozenset({
    "skal",
    "kan",
    "må",
    "er",
    "blir",
    "har",
    "gjeld",
    "gjelder",
    "fastsetter",
    "bestemmer",
    "pålegger",
    "forbyr",
    "tillater",
    "krever",
    "gir",
    "har rett",
    "plikter",
})

# Regex: metadata annotations like "(Oppheva med vedtak ...)" or "(Endra ...)"
_METADATA_ANNOTATION = re.compile(r"^\s*\(Opphev|\s*\(Endra", re.IGNORECASE)

# Regex: pure section header lines like "§ 85.\nD. Om den dømmande makta (§§ 86–91)"
# Matches: § number. Capital-letter-dot  Title  (§§ range)
_SECTION_HEADER_PATTERN = re.compile(
    r"^\s*§\s*\d+[a-z]?\s*\.\s*[A-Z]\.\s+[^.]+\(\s*§§?\s+\d+\s*[-–]\s*\d+\s*\)\s*$",
    re.MULTILINE,
)

# Regex: any § reference in text (used with short-text + no legal verbs check)
_SECTION_REF = re.compile(r"§\s*\d+")

# Regex: lines that look like structural headers rather than legal text
_HEADER_LINE = re.compile(
    r"^(?:"
    r"[A-Z]\.\s+"           # "A. Title"
    r"|§\s*\d+"             # "§ 7"
    r"|\(Opphev"            # "(Oppheva ...)"
    r"|\(Endra"             # "(Endra ...)"
    r")",
)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class ChunkContentValidator:
    """
    Validates individual chunk dicts for substantive legal content.

    A chunk passes validation if it contains real legal text —
    not just section headers, metadata annotations, or structural markers.

    Returns
    -------
    (True, "ok")                  — chunk is valid, proceed to Milvus
    (False, "<reason string>")    — chunk rejected, reason explains why
    """

    def validate(self, chunk: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Main entry point.

        Parameters
        ----------
        chunk : dict
            A chunk dict produced by DigiRettChunker / SectionAwareChunker.
            Expected keys: text, token_count, citation_anchor, chunk_id.

        Returns
        -------
        (is_valid: bool, reason: str)
        """
        text: str = (chunk.get("text") or "").strip()
        token_count: int = chunk.get("token_count") or 0

        if not text:
            # Empty text — should have been caught by validate_chunk already,
            # but guard here too.
            return False, "Empty text"

        # --- Check 1: metadata annotation line ---
        if self._is_metadata_annotation(text, token_count):
            return False, "Metadata annotation only (Oppheva/Endra)"

        # --- Check 2: pure section header pattern ---
        if self._is_section_header_pattern(text):
            return False, "Title-only: section header with § range, no legal text"

        # --- Check 3: all lines are header-like (≤ 3 lines) ---
        if self._all_lines_are_headers(text):
            return False, "Title-only: all lines are structural headers"

        # --- Check 4: short text with § reference but no legal verbs ---
        if self._short_no_legal_verbs(text):
            return False, "Title-only: short § reference with no legal verbs"

        return True, "ok"

    # -----------------------------------------------------------------------
    # Private checks
    # -----------------------------------------------------------------------

    def _is_metadata_annotation(self, text: str, token_count: int) -> bool:
        """
        Catches lines like "(Oppheva med vedtak 18 nov 1905.)"
        Only applies when token count is below the title-only threshold.
        """
        if token_count > 0 and token_count >= TITLE_ONLY_TOKEN_THRESHOLD:
            return False
        return bool(_METADATA_ANNOTATION.match(text))

    def _is_section_header_pattern(self, text: str) -> bool:
        """
        Catches pure structural headers like:
            "§ 85.\nD. Om den dømmande makta (§§ 86 - 91)"
        These are table-of-contents entries, not legal text.
        """
        return bool(_SECTION_HEADER_PATTERN.match(text))

    def _all_lines_are_headers(self, text: str) -> bool:
        """
        For chunks with 1–3 non-empty lines:
        If every line looks like a header (short, starts with letter-dot,
        § reference, or metadata annotation), the chunk is title-only.

        A line is considered a header if it:
          - Starts with a capital letter followed by a dot and space ("A. ")
          - Starts with § and a number
          - Starts with (Oppheva or (Endra
          - Is fewer than 40 characters long
        """
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        if not lines or len(lines) > 3:
            # More than 3 lines → likely has real content, skip this check
            return False

        header_count = sum(
            1 for line in lines
            if _HEADER_LINE.match(line) or len(line) < 40
        )

        return header_count == len(lines)

    def _short_no_legal_verbs(self, text: str) -> bool:
        """
        For very short text (< SHORT_TEXT_CHAR_LIMIT chars) that contains
        a § reference: if none of the Norwegian legal verbs appear,
        the chunk is likely just a section label, not legal text.

        Example: "§ 120 a." → no verbs, has § → title-only
        """
        if len(text) >= SHORT_TEXT_CHAR_LIMIT:
            return False

        if not _SECTION_REF.search(text):
            return False

        text_lower = text.lower()
        return not any(verb in text_lower for verb in LEGAL_VERBS)

def validate_chunk_content(chunk: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Module-level convenience wrapper around ChunkContentValidator.

    Usage in main.py:
        from ingestion.src.processors.chunk_validator import validate_chunk_content

        is_valid, reason = validate_chunk_content(chunk_dict)
        if not is_valid:
            logger.warning("SKIP CHUNK | content | reason=%s", reason)
            continue
    """
    return ChunkContentValidator().validate(chunk)