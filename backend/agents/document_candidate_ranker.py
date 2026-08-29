from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

RRF_K = 60.0

DEFAULT_CHANNEL_WEIGHTS: Dict[str, float] = {
    "title_exact_fuzzy": 3.0,
    "title_bm25": 2.5,
    "statute_ann": 2.0,
    "subdomain_ann": 1.6,
    "domain_ann": 1.3,
    "broad_ann": 1.0,
}


def _doc_id(row: Dict[str, Any]) -> str:
    return str(
        row.get("canonical_document_id")
        or row.get("document_id")
        or ""
    ).strip()


class DocumentCandidateRanker:
    def __init__(
        self,
        channel_weights: Optional[Dict[str, float]] = None,
    ) -> None:
        self._weights = dict(DEFAULT_CHANNEL_WEIGHTS)
        if channel_weights:
            self._weights.update(channel_weights)

    def rank(
        self,
        channels: Dict[str, Sequence[Dict[str, Any]]],
        *,
        limit: int = 12,
        requested_domain: Optional[str] = None,
        requested_subdomains: Optional[Sequence[str]] = None,
        statute_explicit: bool = False,
    ) -> List[Dict[str, Any]]:
        scores: Dict[str, float] = defaultdict(float)
        supports: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        metadata: Dict[str, Dict[str, Any]] = {}
        exact_title_docs = set()
        strong_title_docs = set()

        for channel_name, rows in channels.items():
            if not rows:
                continue

            weight = self._weights.get(channel_name, 1.0)
            if channel_name == "statute_ann" and statute_explicit:
                weight = max(weight, 2.8)

            for rank, row in enumerate(rows, 1):
                did = _doc_id(row)
                if not did:
                    continue

                metadata.setdefault(did, dict(row))
                scores[did] += weight / (RRF_K + rank)
                supports[did].append(
                    {
                        "channel": channel_name,
                        "rank": rank,
                        "weight": weight,
                    }
                )

                if channel_name == "title_exact_fuzzy":
                    match_type = str(row.get("title_match_type") or "")
                    if match_type in {"exact", "exact_core"}:
                        exact_title_docs.add(did)
                    elif match_type in {"strong_containment", "strong_fuzzy"}:
                        strong_title_docs.add(did)

        requested_subs = {str(x) for x in (requested_subdomains or []) if x}

        for did, row in metadata.items():
            # Exact title should not be out-voted by several wrong routing channels.
            if did in exact_title_docs:
                scores[did] += 1.0
            elif did in strong_title_docs:
                scores[did] += 0.08

            # Metadata agreement is a small boost only.  Mismatch never deletes.
            domain_value = str(
                row.get("domain_name")
                or row.get("domain")
                or row.get("domain_id")
                or ""
            ).strip().lower()
            if requested_domain and requested_domain.lower() == domain_value:
                scores[did] += 0.01

            sub_value = str(row.get("subdomain_id") or "").strip()
            if requested_subs and sub_value in requested_subs:
                scores[did] += 0.006

            # Independent channel agreement is useful evidence.
            unique_channels = {x["channel"] for x in supports[did]}
            if len(unique_channels) >= 3:
                scores[did] += 0.008
            elif len(unique_channels) >= 2:
                scores[did] += 0.004

        ranked_ids = sorted(
            scores,
            key=lambda did: scores[did],
            reverse=True,
        )

        result: List[Dict[str, Any]] = []
        for rank, did in enumerate(ranked_ids[:limit], 1):
            row = dict(metadata[did])
            row["canonical_document_id"] = did
            row["document_id"] = did
            row["document_rank"] = rank
            row["document_score"] = float(scores[did])
            row["retrieval_channels"] = supports[did]
            row["exact_title_match"] = did in exact_title_docs
            result.append(row)

        return result
