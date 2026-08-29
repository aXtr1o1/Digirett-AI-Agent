import json
import logging
import os
import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

try:
    from rapidfuzz import fuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False

logger = logging.getLogger(__name__)

_STATUTE_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "registry",
    "statutes.json",
)

_TITLE_STOPWORDS = {
    "forskrift",
    "forskriften",
    "forskrifter",
    "lov",
    "loven",
    "lover",
    "om",
    "til",
    "for",
    "av",
    "og",
    "mv",
}

_LEGAL_TITLE_EQUIVALENTS = {
    "virkeomrade": "anvendelse",
    "anvendelsesomrade": "anvendelse",
}


class StatuteEntry(BaseModel):
    id: str = Field(min_length=3)
    domain: str = Field(min_length=2)
    url: Optional[str] = Field(default=None)
    matched_alias: Optional[str] = Field(default=None)

    @property
    def statute_id(self) -> str:
        return self.id

    @property
    def short_name(self) -> str:
        # Preserve the original public behavior used by QueryReasoningAgent.
        return self.id

    @property
    def document_type(self) -> str:
        sid = self.id.upper()
        if sid.startswith("LOV-"):
            return "LAW"
        if sid.startswith(("FORSKRIFT-", "FOR-", "RES-")):
            return "REGULATION"
        return "UNKNOWN"


class StatuteRegistry:
    def __init__(self, json_path: str = _STATUTE_JSON_PATH) -> None:
        self._table: Dict[str, StatuteEntry] = {}
        self._normalized_alias_map: Dict[str, str] = {}
        self._load_and_validate(json_path)
        logger.info("[OK] StatuteRegistry initialized with %s entries", len(self._table))

    def _load_and_validate(self, json_path: str) -> None:
        if not os.path.exists(json_path):
            logger.error("Missing statute registry file: %s", json_path)
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except Exception as exc:
            logger.error("Failed to parse %s: %s", json_path, exc)
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
                    prev_alias = self._normalized_alias_map[norm_alias]
                    prev_id = self._table[prev_alias].id
                    if prev_id != entry.id:
                        logger.warning(
                            "Duplicate alias collision detected: '%s' -> '%s' conflicts with '%s'",
                            alias,
                            entry.id,
                            prev_id,
                        )
                        duplicates += 1

                self._table[alias] = entry
                self._normalized_alias_map[norm_alias] = alias
            except Exception as val_exc:
                logger.warning("Invalid statute entry for alias '%s': %s", alias, val_exc)

        if duplicates > 0:
            logger.info(
                "Registry startup validation completed | alias conflicts flagged: %s",
                duplicates,
            )

    def lookup(self, query: str) -> Optional[StatuteEntry]:
        if not query:
            return None

        clean_q = self._normalize_key(query)
        if not clean_q:
            return None

        # 1. Exact normalized alias.
        exact = self._lookup_exact(clean_q)
        if exact:
            return exact

        # 2. Exact comparison after conservative legal-title synonym mapping.
        semantic_q = self._normalize_title_terms(clean_q)
        semantic_exact = self._lookup_semantic_exact(semantic_q)
        if semantic_exact:
            return semantic_exact

        requested_type = self._detect_requested_document_type(clean_q)
        typed_aliases = self._candidate_aliases(requested_type)

        # 3. Prefer the longest contained alias of the requested document type.
        contained = self._best_contained_match(clean_q, semantic_q, typed_aliases)
        if contained:
            return contained

        # 4. Fuzzy matching, guarded by distinctive legal-title token overlap.
        fuzzy_match = self._best_fuzzy_match(clean_q, semantic_q, typed_aliases)
        if fuzzy_match:
            return fuzzy_match


        if requested_type:
            return None
        all_aliases = list(self._normalized_alias_map.items())
        contained = self._best_contained_match(clean_q, semantic_q, all_aliases)
        if contained:
            return contained

        return self._best_fuzzy_match(clean_q, semantic_q, all_aliases)

    def lookup_by_id(self, statute_id: str) -> Optional[StatuteEntry]:
        """Look up by LOV/FORSKRIFT/FOR/RES ID directly."""
        wanted = (statute_id or "").strip().upper()
        if not wanted:
            return None
        for alias, entry in self._table.items():
            if entry.id.upper() == wanted:
                return self._enrich(entry, alias)
        return None

    def get_all_ids(self) -> List[str]:
        return list({entry.id for entry in self._table.values()})

    def _lookup_exact(self, clean_q: str) -> Optional[StatuteEntry]:
        orig_alias = self._normalized_alias_map.get(clean_q)
        if not orig_alias:
            return None
        return self._enrich(self._table[orig_alias], orig_alias)

    def _lookup_semantic_exact(self, semantic_q: str) -> Optional[StatuteEntry]:
        matches: List[Tuple[int, str]] = []
        for norm_alias, orig_alias in self._normalized_alias_map.items():
            if self._normalize_title_terms(norm_alias) == semantic_q:
                matches.append((len(norm_alias), orig_alias))
        if not matches:
            return None
        _, alias = max(matches, key=lambda item: item[0])
        logger.info("Semantic-exact statute match: '%s'", alias)
        return self._enrich(self._table[alias], alias)

    def _candidate_aliases(self, requested_type: Optional[str]) -> List[Tuple[str, str]]:
        if not requested_type:
            return list(self._normalized_alias_map.items())

        candidates: List[Tuple[str, str]] = []
        for norm_alias, orig_alias in self._normalized_alias_map.items():
            entry = self._table[orig_alias]
            if entry.document_type == requested_type:
                candidates.append((norm_alias, orig_alias))
        return candidates

    def _best_contained_match(
        self,
        clean_q: str,
        semantic_q: str,
        candidates: Sequence[Tuple[str, str]],
    ) -> Optional[StatuteEntry]:
        matches: List[Tuple[int, int, str]] = []

        for norm_alias, orig_alias in candidates:
            if not norm_alias:
                continue

            semantic_alias = self._normalize_title_terms(norm_alias)
            raw_contained = norm_alias in clean_q
            semantic_contained = semantic_alias in semantic_q
            if not raw_contained and not semantic_contained:
                continue

            distinctive = self._distinctive_tokens(semantic_alias)
            # Ignore extremely generic aliases (e.g. only "forskrift om") as
            # deterministic contained matches.
            if not distinctive:
                continue

            matches.append((len(distinctive), len(norm_alias), orig_alias))

        if not matches:
            return None

        _, _, alias = max(matches, key=lambda item: (item[0], item[1]))
        logger.info("Contained statute match: '%s'", alias)
        return self._enrich(self._table[alias], alias)

    def _best_fuzzy_match(
        self,
        clean_q: str,
        semantic_q: str,
        candidates: Sequence[Tuple[str, str]],
    ) -> Optional[StatuteEntry]:
        if len(clean_q) <= 4:
            return None

        q_tokens = self._distinctive_tokens(semantic_q)
        if not q_tokens:
            return None

        scored: List[Tuple[float, float, int, str]] = []
        for norm_alias, orig_alias in candidates:
            semantic_alias = self._normalize_title_terms(norm_alias)
            alias_tokens = self._distinctive_tokens(semantic_alias)
            if not alias_tokens:
                continue

            overlap = len(q_tokens & alias_tokens)
            min_required = 1 if min(len(q_tokens), len(alias_tokens)) <= 2 else 2
            if overlap < min_required:
                continue

            overlap_ratio = overlap / max(1, len(alias_tokens))

            if _RAPIDFUZZ_AVAILABLE:
                title_score = float(fuzz.token_set_ratio(semantic_q, semantic_alias))
                order_score = float(fuzz.ratio(semantic_q, semantic_alias))
            else:
                import difflib

                title_score = 100.0 * difflib.SequenceMatcher(
                    None, semantic_q, semantic_alias
                ).ratio()
                order_score = title_score

            combined = (0.55 * title_score) + (0.25 * order_score) + (20.0 * overlap_ratio)
            scored.append((combined, title_score, len(norm_alias), orig_alias))

        if not scored:
            return None

        combined, title_score, _, alias = max(
            scored, key=lambda item: (item[0], item[1], item[2])
        )

        # A conservative threshold prevents a generic regulation title from being
        # forced when the query does not sufficiently resemble any registry alias.
        if combined < 78.0 or title_score < 70.0:
            return None

        logger.info(
            "Fuzzy statute match: '%s' -> '%s' (combined=%.1f, title=%.1f)",
            clean_q,
            alias,
            combined,
            title_score,
        )
        return self._enrich(self._table[alias], alias)

    @staticmethod
    def _detect_requested_document_type(clean_q: str) -> Optional[str]:
        # Explicit regulation wording takes precedence because regulation titles
        # frequently contain a parent law name (e.g. "arbeidsmiljølovens").
        if re.search(r"\bforskrift(?:en|er|ene|s)?\b", clean_q):
            return "REGULATION"
        if re.search(r"\b(?:lov|loven|lover|lovens)\b", clean_q) or clean_q.startswith("lov-"):
            return "LAW"
        return None

    @classmethod
    def _normalize_title_terms(cls, text: str) -> str:
        tokens = text.split()
        normalized = [_LEGAL_TITLE_EQUIVALENTS.get(tok, tok) for tok in tokens]
        return " ".join(normalized)

    @classmethod
    def _distinctive_tokens(cls, text: str) -> set:
        return {
            token
            for token in text.split()
            if len(token) >= 4 and token not in _TITLE_STOPWORDS
        }

    @staticmethod
    def _normalize_key(text: str) -> str:
        if not text:
            return ""
        s = text.lower().strip()
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = re.sub(r"[^\w\s-]", "", s)
        return re.sub(r"\s+", " ", s).strip()

    def _enrich(self, entry: StatuteEntry, alias: Optional[str] = None) -> StatuteEntry:
        enriched = entry.model_copy()
        if alias:
            enriched.matched_alias = alias
        if not enriched.url:
            enriched.url = _id_to_url(enriched.id)
        return enriched


def _id_to_url(statute_id: str) -> str:
    if not statute_id:
        return ""

    sid = statute_id.strip()
    sid_upper = sid.upper()

    if sid_upper.startswith("LOV-"):
        path = "lov"
        date_num = sid[4:]
    elif sid_upper.startswith("FORSKRIFT-"):
        path = "forskrift"
        date_num = sid[10:]
    elif sid_upper.startswith("FOR-"):
        path = "forskrift"
        date_num = sid[4:]
    elif sid_upper.startswith("RES-"):
        path = "forskrift"
        date_num = sid[4:]
    else:
        return ""

    parts = date_num.split("-")
    if len(parts) != 4:
        return ""

    year, month, day, num = parts
    try:
        num_clean = str(int(num))
    except ValueError:
        num_clean = num
    return f"https://lovdata.no/dokument/NL/{path}/{year}-{month}-{day}-{num_clean}"


# Module-level singleton
_registry = StatuteRegistry()


def get_registry() -> StatuteRegistry:
    return _registry
