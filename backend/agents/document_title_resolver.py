"""
agents/document_title_resolver.py

Document-level exact/fuzzy/lexical title discovery.

This deliberately searches the legal-document catalogue rather than chunks.
An exact document title is therefore not dependent on router accuracy or ANN
chunk competition.
"""

from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

try:
    from rank_bm25 import BM25Okapi
    _BM25_AVAILABLE = True
except Exception:
    BM25Okapi = None
    _BM25_AVAILABLE = False


def _fold(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").lower())
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.replace("æ", "ae").replace("ø", "o").replace("å", "a")
    # Common Bokmål/Nynorsk morphology that is safe for title matching.
    value = value.replace("offentleggjering", "offentliggjoring")
    value = value.replace("offentliggjøring", "offentliggjoring")
    value = value.replace("anvendelsesomrade", "anvendelse")
    value = value.replace("virkeomrade", "anvendelse")
    value = re.sub(r"[^a-z0-9§]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _strip_legal_prefix(text: str) -> str:
    value = _fold(text)
    value = re.sub(
        r"^(forskrift(?:er)?|lov|vedtak|overgangsregler|overgangsbestemmelser)\s+(om|til)?\s*",
        "",
        value,
    )
    return value.strip()


def _tokens(text: str) -> List[str]:
    stop = {
        "om", "og", "i", "av", "til", "for", "den", "det", "de", "mv",
        "med", "som", "pa", "på", "etter", "lov", "forskrift", "forskrifter",
    }
    return [
        w for w in re.findall(r"\b[a-z0-9]{2,}\b", _fold(text))
        if w not in stop
    ]


def _token_f1(a: str, b: str) -> float:
    aa, bb = set(_tokens(a)), set(_tokens(b))
    if not aa or not bb:
        return 0.0
    inter = len(aa & bb)
    if inter == 0:
        return 0.0
    p = inter / len(aa)
    r = inter / len(bb)
    return (2 * p * r) / (p + r)


def _requested_document_type(query: str) -> Optional[str]:
    q = _fold(query)
    # Regulation wins because a regulation title can contain a parent law name.
    if "forskrift" in q:
        return "REGULATION"
    if q.startswith("lov ") or " loven " in f" {q} " or q.endswith("loven"):
        return "LAW"
    return None


class DocumentTitleResolver:
    def __init__(self, search_backend: Any) -> None:
        self._backend = search_backend

    def _score(self, query: str, title: str) -> Tuple[float, str]:
        q_full = _fold(query)
        t_full = _fold(title)
        q_core = _strip_legal_prefix(query)
        t_core = _strip_legal_prefix(title)

        if q_full and q_full == t_full:
            return 3.0, "exact"
        if q_core and q_core == t_core:
            return 2.8, "exact_core"

        seq = difflib.SequenceMatcher(None, q_core or q_full, t_core or t_full).ratio()
        tf1 = _token_f1(query, title)
        containment = 0.0
        if q_core and t_core and (q_core in t_core or t_core in q_core):
            containment = 1.0

        score = 0.50 * seq + 0.40 * tf1 + 0.10 * containment
        if containment and tf1 >= 0.65:
            match_type = "strong_containment"
        elif score >= 0.72:
            match_type = "strong_fuzzy"
        else:
            match_type = "fuzzy"
        return score, match_type

    def fuzzy_candidates(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        requested_type = _requested_document_type(query)
        rows: List[Dict[str, Any]] = []

        for doc in self._backend.get_document_catalog():
            title = str(doc.get("doc_title") or "")
            if not title:
                continue

            score, match_type = self._score(query, title)
            doc_type = str(doc.get("document_type") or "").upper()

            # Type is a ranking signal, not a hard exclusion.
            if requested_type and doc_type == requested_type:
                score += 0.08
            elif requested_type and doc_type and doc_type != requested_type:
                score -= 0.08

            item = dict(doc)
            item["score"] = float(score)
            item["title_score"] = float(score)
            item["title_match_type"] = match_type
            rows.append(item)

        rows.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
        return rows[:limit]

    def lexical_candidates(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        docs = self._backend.get_document_catalog()
        if not docs:
            return []

        requested_type = _requested_document_type(query)
        query_tokens = _tokens(query)

        if _BM25_AVAILABLE and query_tokens:
            corpus = [_tokens(str(d.get("doc_title") or "")) for d in docs]
            model = BM25Okapi(corpus)
            scores = model.get_scores(query_tokens)
        else:
            scores = [_token_f1(query, str(d.get("doc_title") or "")) for d in docs]

        ranked = sorted(
            range(len(docs)),
            key=lambda i: float(scores[i]),
            reverse=True,
        )

        rows: List[Dict[str, Any]] = []
        for idx in ranked[:limit]:
            item = dict(docs[idx])
            score = float(scores[idx])
            if requested_type:
                dt = str(item.get("document_type") or "").upper()
                if dt == requested_type:
                    score += 0.05
            item["score"] = score
            item["title_bm25_score"] = score
            rows.append(item)
        return rows

    def discover(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "title_exact_fuzzy": self.fuzzy_candidates(query, limit=limit),
            "title_bm25": self.lexical_candidates(query, limit=limit),
        }
