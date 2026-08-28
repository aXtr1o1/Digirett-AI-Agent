from __future__ import annotations

import logging
import re
from typing import Any, Dict, Tuple, Union

from ingestion.models.legal_section import StructuralChunk

logger = logging.getLogger(__name__)

# Heuristic positive signal (not mandatory for validity)
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

# Obvious repealed metadata annotations without legal content
_METADATA_ANNOTATION = re.compile(
    r"^\s*\((?:opphevet|oppheva|endra|opph|tilføyd)\b[^)]*\)\s*$",
    re.IGNORECASE,
)

# Obvious TOC section range header: e.g. "§ 85.\nD. Om den dømmande makta (§§ 86–91)"
_TOC_RANGE_PATTERN = re.compile(
    r"^\s*§\s*\d+[a-z]?\s*\.\s*[A-Z]\.\s+[^.]+\(\s*§§?\s+\d+\s*[-–]\s*\d+\s*\)\s*$",
    re.MULTILINE,
)

# Pure changelog / amendment noise
_CHANGELOG_NOISE = re.compile(
    r"^\s*(?:endret ved lov|opphevet ved lov|tilføyd ved lov|endret ved forskrift)\b",
    re.IGNORECASE,
)


class ChunkContentValidator:
    def validate(self, chunk: Union[Dict[str, Any], StructuralChunk]) -> Tuple[bool, str]:
        """
        Validates a chunk dict or StructuralChunk instance.
        """
        if isinstance(chunk, StructuralChunk):
            text = (chunk.source_text or "").strip()
        elif isinstance(chunk, dict):
            text = (chunk.get("text") or chunk.get("source_text") or "").strip()
        else:
            return False, "Invalid chunk type"

        if not text:
            return False, "Empty text"

        # Check 1: Pure repeal/metadata annotation stub
        if _METADATA_ANNOTATION.match(text):
            return False, "Repeal/metadata annotation stub only"

        # Check 2: Pure TOC range header
        if _TOC_RANGE_PATTERN.match(text):
            return False, "TOC section header range only"

        # Check 3: Obvious changelog / amendment noise if short
        if len(text) < 120 and _CHANGELOG_NOISE.match(text):
            return False, "Short amendment changelog noise"

        # Check 4: Extremely short non-substantive text (e.g. just "§ 12")
        if len(text) < 15 and re.match(r"^§\s*\d+[a-z]?(?:-\d+)?\.?$", text, re.IGNORECASE):
            return False, "Section number header only with no text"

        return True, "ok"


def validate_chunk_content(chunk: Union[Dict[str, Any], StructuralChunk]) -> Tuple[bool, str]:
    """Module-level convenience wrapper."""
    return ChunkContentValidator().validate(chunk)
