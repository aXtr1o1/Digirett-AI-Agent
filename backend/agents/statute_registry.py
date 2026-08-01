"""
agents/statute_registry.py — Deterministic & Fuzzy Norwegian Statute Registry

Refactored per TL Code Review Guidelines:
1. Static data externalization — loads from registry/statutes.json at startup.
2. Startup schema & duplicate normalized alias validation via StatuteEntry(BaseModel).
3. Fuzzy fallback matching using RapidFuzz / difflib token distance on exact lookup miss.
"""

import json
import logging
import os
import re
import unicodedata
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

try:
    from rapidfuzz import process, fuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False

logger = logging.getLogger(__name__)

_STATUTE_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "registry",
    "statutes.json",
)


class StatuteEntry(BaseModel):
    id: str = Field(min_length=3)
    domain: str = Field(min_length=2)
    url: Optional[str] = Field(default=None)

    @property
    def statute_id(self) -> str:
        return self.id

    @property
    def short_name(self) -> str:
        return self.id



class StatuteRegistry:

    def __init__(self, json_path: str = _STATUTE_JSON_PATH) -> None:
        self._table: Dict[str, StatuteEntry] = {}
        self._normalized_alias_map: Dict[str, str] = {}
        self._load_and_validate(json_path)
        logger.info(f"[OK] StatuteRegistry initialized with {len(self._table)} entries")

    def _load_and_validate(self, json_path: str) -> None:
        if not os.path.exists(json_path):
            logger.error(f"❌ Missing statute registry file: {json_path}")
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except Exception as exc:
            logger.error(f"❌ Failed to parse {json_path}: {exc}")
            return

        duplicates = 0
        for alias, item in raw_data.items():
            if not isinstance(item, dict):
                continue

            try:
                entry = StatuteEntry(
                    id=item.get("id", ""),
                    domain=item.get("domain", ""),
                    url=item.get("url"),
                )
                norm_alias = self._normalize_key(alias)

                if norm_alias in self._normalized_alias_map:
                    prev_id = self._table[self._normalized_alias_map[norm_alias]].id
                    if prev_id != entry.id:
                        logger.warning(
                            f"⚠️ Duplicate alias collision detected: '{alias}' -> '{entry.id}' conflicts with '{prev_id}'"
                        )
                        duplicates += 1

                self._table[alias] = entry
                self._normalized_alias_map[norm_alias] = alias
            except Exception as val_exc:
                logger.warning(f"⚠️ Invalid statute entry for alias '{alias}': {val_exc}")

        if duplicates > 0:
            logger.info(f"Registry startup validation completed | alias conflicts flagged: {duplicates}")

    def lookup(self, query: str) -> Optional[StatuteEntry]:
        """
        Looks up a Norwegian statute by exact normalized key or fuzzy fallback.
        """
        if not query:
            return None

        clean_q = self._normalize_key(query)

        # 1. Exact match against normalized alias map
        if clean_q in self._normalized_alias_map:
            orig_alias = self._normalized_alias_map[clean_q]
            return self._enrich(self._table[orig_alias])

        # 2. Tokenized exact match
        for norm_alias, orig_alias in self._normalized_alias_map.items():
            if norm_alias and norm_alias in clean_q:
                return self._enrich(self._table[orig_alias])

        # 3. Fuzzy fallback matching on exact lookup miss
        choices = list(self._normalized_alias_map.keys())
        if _RAPIDFUZZ_AVAILABLE and len(clean_q) > 4:
            match = process.extractOne(clean_q, choices, scorer=fuzz.WRatio, score_cutoff=75.0)
            if match:
                matched_norm = match[0]
                orig_alias = self._normalized_alias_map[matched_norm]
                logger.info(f"Fuzzy statute match (RapidFuzz): '{query}' -> '{orig_alias}' (score={match[1]:.1f})")
                return self._enrich(self._table[orig_alias])
        elif len(clean_q) > 4:
            import difflib
            matches = difflib.get_close_matches(clean_q, choices, n=1, cutoff=0.7)
            if matches:
                matched_norm = matches[0]
                orig_alias = self._normalized_alias_map[matched_norm]
                logger.info(f"Fuzzy statute match (difflib): '{query}' -> '{orig_alias}'")
                return self._enrich(self._table[orig_alias])


        return None

    def lookup_by_id(self, statute_id: str) -> Optional[StatuteEntry]:
        """Look up by LOV/FORSKRIFT ID directly."""
        for entry in self._table.values():
            if entry.id == statute_id:
                return self._enrich(entry)
        return None

    def get_all_ids(self) -> List[str]:
        return list({entry.id for entry in self._table.values()})

    @staticmethod
    def _normalize_key(text: str) -> str:
        if not text:
            return ""
        s = text.lower().strip()
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = re.sub(r"[^\w\s-]", "", s)
        return re.sub(r"\s+", " ", s).strip()

    def _enrich(self, entry: StatuteEntry) -> StatuteEntry:
        enriched = entry.model_copy()
        if not enriched.url:
            enriched.url = _id_to_url(enriched.id)
        return enriched


def _id_to_url(statute_id: str) -> str:
    if not statute_id:
        return ""
    sid = statute_id.strip()
    if sid.upper().startswith("LOV-"):
        path = "lov"
        date_num = sid[4:]
    elif sid.upper().startswith("FORSKRIFT-"):
        path = "forskrift"
        date_num = sid[10:]
    else:
        return ""
    parts = date_num.split("-")
    if len(parts) == 4:
        year, month, day, num = parts
        try:
            num_clean = str(int(num))
        except ValueError:
            num_clean = num
        return f"https://lovdata.no/dokument/NL/{path}/{year}-{month}-{day}-{num_clean}"
    return ""


# Module-level singleton
_registry = StatuteRegistry()


def get_registry() -> StatuteRegistry:
    return _registry