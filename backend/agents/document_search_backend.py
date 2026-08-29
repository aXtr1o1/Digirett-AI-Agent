"""
agents/document_search_backend.py

Low-level, read-only Milvus access used by the document-first retriever.

This module intentionally DOES NOT change db.milvus_client.MilvusClient's
public contract.  It wraps the already-connected MilvusClient and exposes
explicit retrieval channels so router output is a signal rather than a
single hard gate.

Channels:
- statute constrained ANN
- domain + subdomain ANN
- domain ANN
- broad corpus ANN
- ANN restricted to an already-ranked set of documents
- cached document catalogue for title/alias retrieval
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)


# Application canonical domain -> production Milvus domain_id.
CANONICAL_DOMAIN_TO_ID: Dict[str, str] = {
    "selskapsrett": "D01_COMPANY",
    "manda_fusjon_fisjon": "D02_MA",
    "arsregnskap_og_selskapsrapportering": "D03_ACCOUNTS",
    "avtalerett": "D04_CONTRACT",
    "obligasjonsrett": "D05_OBLIGATIONS",
    "inkasso_og_tvangsfullbyrdelse": "D06_DEBT",
    "konkursrett_og_insolvens": "D07_INSOLVENCY",
    "pengekravsrett_fordringer": "D08_MONETARY",
    "panterett_og_sikkerhetsrett": "D09_SECURITY",
    "tvistelosning_smb": "D10_DISPUTE",
    "arbeidsrett": "D12_EMPLOYMENT",
    "personvern_gdpr_business_compliance": "D12_PRIVACY",
}

CATALOG_CACHE_SECONDS = 300.0
CATALOG_QUERY_LIMIT = 16384


def _escape_milvus_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


class DocumentSearchBackend:
    """
    Thin compatibility layer over the project's existing MilvusClient.

    The existing MilvusClient stays untouched.  This class only relies on the
    connection state already exposed by it (`_collection`, `_schema_fields`),
    exactly like the diagnostic script that was successfully run against the
    production collection.
    """

    _OUTPUT_FIELDS = [
        "chunk_id",
        "legal_document_id",
        "legal_section_id",
        "canonical_document_id",
        "source_section_key",
        "source_url",
        "doc_title",
        "document_type",
        "section_number",
        "section_title",
        "citation_anchor",
        "domain_id",
        "domain_name",
        "subdomain_id",
        "subdomain_name",
        "parent_law_canonical_id",
        "parent_law_title",
        "relationship_type",
        "source_type",
        "b2b_b2c",
        "tier",
        "jurisdiction",
        "version_date",
        "is_current",
        "retrieval_enabled",
        "text",
    ]

    def __init__(self, milvus_client: Any) -> None:
        self._milvus = milvus_client
        self._catalog_cache: List[Dict[str, Any]] = []
        self._catalog_cached_at = 0.0
        self._catalog_entity_count: Optional[int] = None

    # ------------------------------------------------------------------
    # Connection/schema helpers
    # ------------------------------------------------------------------
    @property
    def collection(self) -> Any:
        collection = getattr(self._milvus, "_collection", None)
        if collection is None:
            raise RuntimeError(
                "Milvus collection is not initialized. "
                "The application's existing MilvusClient.connect() must run first."
            )
        ensure_loaded = getattr(self._milvus, "_ensure_loaded", None)
        if callable(ensure_loaded):
            ensure_loaded()
        return collection

    @property
    def schema_fields(self) -> set:
        fields = getattr(self._milvus, "_schema_fields", None)
        if fields:
            return set(fields)
        try:
            return {f.name for f in self.collection.schema.fields}
        except Exception:
            return set()

    def _output_fields(self) -> List[str]:
        fields = self.schema_fields
        return [f for f in self._OUTPUT_FIELDS if f in fields]

    # ------------------------------------------------------------------
    # Catalogue
    # ------------------------------------------------------------------
    def get_document_catalog(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Return one representative row per retrieval-enabled legal document.

        The current corpus is ~12.5k chunks, so a single <=16384 query is enough.
        A warning is emitted if the collection grows beyond that boundary.
        """
        now = time.monotonic()
        entity_count: Optional[int] = None
        try:
            entity_count = int(self.collection.num_entities)
        except Exception:
            pass

        cache_fresh = (
            self._catalog_cache
            and not force_refresh
            and (now - self._catalog_cached_at) < CATALOG_CACHE_SECONDS
            and (
                self._catalog_entity_count is None
                or entity_count is None
                or entity_count == self._catalog_entity_count
            )
        )
        if cache_fresh:
            return [dict(x) for x in self._catalog_cache]

        fields = self._output_fields()
        expr = (
            "retrieval_enabled == True"
            if "retrieval_enabled" in self.schema_fields
            else 'canonical_document_id != ""'
        )

        if entity_count and entity_count > CATALOG_QUERY_LIMIT:
            logger.warning(
                "Document catalogue query limit=%s but collection contains %s entities. "
                "Increase CATALOG_QUERY_LIMIT or add query pagination before the corpus grows further.",
                CATALOG_QUERY_LIMIT,
                entity_count,
            )

        rows = self.collection.query(
            expr=expr,
            output_fields=fields,
            limit=CATALOG_QUERY_LIMIT,
        )

        docs: Dict[str, Dict[str, Any]] = {}
        variants: Dict[str, Dict[str, set]] = defaultdict(lambda: defaultdict(set))

        for row in rows:
            did = str(row.get("canonical_document_id") or "").strip()
            if not did:
                continue

            if did not in docs:
                docs[did] = {
                    "canonical_document_id": did,
                    "document_id": did,
                    "doc_title": row.get("doc_title") or "",
                    "document_type": row.get("document_type") or "",
                    "domain_id": row.get("domain_id") or "",
                    "domain_name": row.get("domain_name") or "",
                    "subdomain_id": row.get("subdomain_id") or "",
                    "subdomain_name": row.get("subdomain_name") or "",
                    "jurisdiction": row.get("jurisdiction") or "",
                    "b2b_b2c": row.get("b2b_b2c") or "",
                    "parent_law_canonical_id": row.get("parent_law_canonical_id") or "",
                    "parent_law_title": row.get("parent_law_title") or "",
                    "source_url": row.get("source_url") or "",
                    "retrieval_enabled": row.get("retrieval_enabled", True),
                    "is_current": row.get("is_current"),
                    "version_date": row.get("version_date") or "",
                    "chunk_count": 0,
                }

            docs[did]["chunk_count"] += 1

            # Prefer non-empty representative values if the first chunk was sparse.
            for f in (
                "doc_title",
                "document_type",
                "domain_id",
                "domain_name",
                "subdomain_id",
                "subdomain_name",
                "jurisdiction",
                "b2b_b2c",
                "parent_law_canonical_id",
                "parent_law_title",
                "source_url",
            ):
                value = row.get(f)
                if value not in (None, ""):
                    variants[did][f].add(str(value))
                    if not docs[did].get(f):
                        docs[did][f] = value

        result = []
        for did, doc in docs.items():
            doc["metadata_variants"] = {
                k: sorted(v) for k, v in variants[did].items()
            }
            result.append(doc)

        result.sort(key=lambda x: x["canonical_document_id"])
        self._catalog_cache = [dict(x) for x in result]
        self._catalog_cached_at = now
        self._catalog_entity_count = entity_count
        return result

    # ------------------------------------------------------------------
    # Filter builders
    # ------------------------------------------------------------------
    def _domain_id(self, domain: Optional[str]) -> Optional[str]:
        if not domain:
            return None
        value = str(domain).strip()
        if value.startswith("D") and "_" in value:
            return value
        return CANONICAL_DOMAIN_TO_ID.get(value.lower(), value)

    def _statute_expr(self, statute_filter: Optional[str]) -> Optional[str]:
        """
        Build precise statute clauses.

        Important:
        - comma-separated filters are split independently;
        - a LAW may include explicitly linked regulations through parent_law;
        - REGULATION never means "any regulation";
        - no global `OR document_type == "REGULATION"` wildcard is emitted.
        """
        if not statute_filter:
            return None

        schema = self.schema_fields
        clauses: List[str] = []

        for raw_token in str(statute_filter).split(","):
            token = raw_token.strip()
            if not token:
                continue

            low = token.lower()
            date_match = re.search(r"(\d{4}-\d{2}-\d{2}-\d+)", token)
            if not date_match:
                continue
            date_part = date_match.group(1)

            doc_kind: Optional[str] = None
            if "/forskrift/" in low or re.match(r"^(for|forskrift|res)-", low):
                doc_kind = "REGULATION"
            elif "/lov/" in low or re.match(r"^lov-", low):
                doc_kind = "LAW"

            local: List[str] = []

            if "canonical_document_id" in schema:
                if doc_kind == "REGULATION":
                    local.append(
                        f'canonical_document_id like "%/forskrift/{_escape_milvus_string(date_part)}"'
                    )
                elif doc_kind == "LAW":
                    local.append(
                        f'canonical_document_id like "%/lov/{_escape_milvus_string(date_part)}"'
                    )
                else:
                    local.append(
                        f'canonical_document_id like "%/{_escape_milvus_string(date_part)}"'
                    )

            if "source_url" in schema:
                local.append(
                    f'source_url like "%{_escape_milvus_string(date_part)}%"'
                )

            # A law can intentionally pull regulations explicitly linked to it.
            if doc_kind == "LAW" and "parent_law_canonical_id" in schema:
                dp = _escape_milvus_string(date_part)
                local.extend(
                    [
                        f'parent_law_canonical_id == "NL/lov/{dp}"',
                        f'parent_law_canonical_id == "LTI/lov/{dp}"',
                        f'parent_law_canonical_id like "%/lov/{dp}"',
                    ]
                )

            if local:
                clause = f"({' or '.join(local)})"
                if doc_kind and "document_type" in schema and doc_kind == "REGULATION":
                    # For regulation URLs, keep the identity precise.
                    clause = f"({clause} and document_type == \"REGULATION\")"
                clauses.append(clause)

        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return f"({' or '.join(clauses)})"

    def build_channel_expr(
        self,
        *,
        domain: Optional[str] = None,
        subdomains: Optional[Sequence[str]] = None,
        jurisdiction: Optional[str] = None,
        b2b_b2c: Optional[str] = None,
        statute_filter: Optional[str] = None,
        document_ids: Optional[Sequence[str]] = None,
    ) -> Optional[str]:
        schema = self.schema_fields
        parts: List[str] = []

        if "retrieval_enabled" in schema:
            parts.append("retrieval_enabled == True")

        statute_expr = self._statute_expr(statute_filter)
        if statute_expr:
            parts.append(statute_expr)

        if document_ids and "canonical_document_id" in schema:
            ids = [str(x).strip() for x in document_ids if str(x).strip()]
            if ids:
                values = ", ".join(
                    f'"{_escape_milvus_string(x)}"' for x in sorted(set(ids))
                )
                parts.append(f"canonical_document_id in [{values}]")

        domain_id = self._domain_id(domain)
        if domain_id:
            if "domain_id" in schema:
                parts.append(
                    f'domain_id == "{_escape_milvus_string(domain_id)}"'
                )
            elif "domain_name" in schema:
                parts.append(
                    f'domain_name == "{_escape_milvus_string(str(domain))}"'
                )

        sub_list = [str(x).strip() for x in (subdomains or []) if str(x).strip()]
        if sub_list and "subdomain_id" in schema:
            if len(sub_list) == 1:
                parts.append(
                    f'subdomain_id == "{_escape_milvus_string(sub_list[0])}"'
                )
            else:
                values = ", ".join(
                    f'"{_escape_milvus_string(x)}"' for x in sorted(set(sub_list))
                )
                parts.append(f"subdomain_id in [{values}]")

        if jurisdiction and str(jurisdiction).upper() != "BOTH" and "jurisdiction" in schema:
            j = _escape_milvus_string(str(jurisdiction).upper())
            parts.append(f'(jurisdiction == "{j}" or jurisdiction == "BOTH")')

        if b2b_b2c and str(b2b_b2c).upper() != "BOTH" and "b2b_b2c" in schema:
            b = _escape_milvus_string(str(b2b_b2c).upper())
            parts.append(f'(b2b_b2c == "{b}" or b2b_b2c == "BOTH")')

        return " and ".join(parts) if parts else None

    # ------------------------------------------------------------------
    # ANN
    # ------------------------------------------------------------------
    def _search_params(self, limit: int) -> Dict[str, Any]:
        metric_type = "COSINE"
        try:
            from config import settings
            metric_type = getattr(settings, "MILVUS_METRIC_TYPE", None) or "COSINE"
        except Exception:
            pass

        index_type = "HNSW"
        try:
            indexes = self.collection.indexes
            if indexes:
                index_type = (
                    indexes[0].params.get("index_type") or "HNSW"
                ).upper()
        except Exception:
            pass

        params: Dict[str, Any] = {}
        if "HNSW" in index_type:
            # Wider than the old hard-coded ef=256, but bounded for latency.
            params["ef"] = max(256, min(2048, int(limit) * 4))
        elif "IVF" in index_type:
            params["nprobe"] = 128

        return {"metric_type": metric_type, "params": params}

    def search_ann(
        self,
        embedding: List[float],
        *,
        limit: int,
        domain: Optional[str] = None,
        subdomains: Optional[Sequence[str]] = None,
        jurisdiction: Optional[str] = None,
        b2b_b2c: Optional[str] = None,
        statute_filter: Optional[str] = None,
        document_ids: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        fields = self._output_fields()
        expr = self.build_channel_expr(
            domain=domain,
            subdomains=subdomains,
            jurisdiction=jurisdiction,
            b2b_b2c=b2b_b2c,
            statute_filter=statute_filter,
            document_ids=document_ids,
        )

        logger.debug(
            "DocumentSearchBackend.search_ann | limit=%s | expr=%r",
            limit,
            expr,
        )

        results = self.collection.search(
            data=[embedding],
            anns_field="embedding",
            param=self._search_params(limit),
            limit=int(limit),
            output_fields=fields,
            expr=expr,
        )

        hits: List[Dict[str, Any]] = []
        for batch in results:
            for hit in batch:
                row: Dict[str, Any] = {"score": float(hit.distance)}
                for field in fields:
                    value = getattr(hit.entity, field, None)
                    if value is None and hasattr(hit.entity, "get"):
                        value = hit.entity.get(field)
                    row[field] = value

                # Preserve every alias expected by the existing downstream code.
                source_url = row.get("source_url") or ""
                canonical_id = (
                    row.get("canonical_document_id")
                    or row.get("source_section_key")
                    or ""
                )
                row["source_doc_url"] = source_url
                row["url"] = source_url
                row["file_name"] = source_url
                row["document_id"] = canonical_id
                row["section_ref"] = (
                    row.get("section_number")
                    or row.get("citation_anchor")
                    or ""
                )
                row["domain"] = row.get("domain_name") or row.get("domain_id") or ""
                row["subdomain"] = (
                    row.get("subdomain_name")
                    or row.get("subdomain_id")
                    or ""
                )
                row["law_title"] = row.get("doc_title") or ""
                hits.append(row)
        return hits

    def search_within_documents(
        self,
        embedding: List[float],
        document_ids: Sequence[str],
        *,
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not document_ids:
            return []
        return self.search_ann(
            embedding,
            limit=limit,
            document_ids=document_ids,
        )
