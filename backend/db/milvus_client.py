import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from pymilvus import Collection, connections, utility
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class MilvusConfig(BaseModel):
    host: str
    port: int
    collection_name: str
    alias: str = Field(default="default")
    timeout: float = Field(default=10.0)
_DOMAIN_CANONICAL_TO_ID = {
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

_DOMAIN_CANONICAL_TO_NAME = {
    "selskapsrett": "Selskapsrett",
    "manda_fusjon_fisjon": "M&A / Fusjon / Fisjon",
    "arsregnskap_og_selskapsrapportering": "Årsregnskap og selskapsrapportering",
    "avtalerett": "Avtalerett",
    "obligasjonsrett": "Obligasjonsrett",
    "inkasso_og_tvangsfullbyrdelse": "Inkasso og tvangsfullbyrdelse",
    "konkursrett_og_insolvens": "Konkursrett og insolvens",
    "pengekravsrett_fordringer": "Pengekravsrett / fordringer",
    "panterett_og_sikkerhetsrett": "Panterett og sikkerhetsrett",
    "tvistelosning_smb": "Tvisteløsning SMB",
    "arbeidsrett": "Arbeidsrett",
    "personvern_gdpr_business_compliance": "Personvern / GDPR",
}


class MilvusFilterBuilder:
    """Standalone builder for Milvus boolean filter expressions."""

    @staticmethod
    def _escape(value: str) -> str:
        return str(value).replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _split_statute_filters(statute_filter: Optional[str]) -> List[str]:
        
        if not statute_filter:
            return []
        return [part.strip() for part in str(statute_filter).split(",") if part.strip()]

    @classmethod
    def _parse_statute_token(cls, token: str) -> Tuple[Optional[str], str]:
        """Return (date-number, document_type) for URL/ID/canonical-id input."""
        raw = (token or "").strip()
        if not raw:
            return None, "UNKNOWN"

        upper = raw.upper()
        doc_type = "UNKNOWN"

        if upper.startswith("LOV-"):
            doc_type = "LAW"
        elif upper.startswith(("FORSKRIFT-", "FOR-", "RES-")):
            doc_type = "REGULATION"
        elif "/FORSKRIFT/" in upper:
            doc_type = "REGULATION"
        elif "/LOV/" in upper:
            doc_type = "LAW"

        match = re.search(r"(\d{4}-\d{2}-\d{2}-\d+)", raw)
        if not match:
            return None, doc_type
        return match.group(1), doc_type

    @classmethod
    def _single_statute_expr(
        cls,
        token: str,
        schema_fields: Set[str],
        include_linked_regulations: bool = True,
    ) -> str:
        date_part, doc_type = cls._parse_statute_token(token)
        if not date_part:
            return ""

        date_escaped = cls._escape(date_part)
        if "canonical_document_id" in schema_fields:
            if doc_type == "LAW":
                own_doc_clause = (
                    f'canonical_document_id like "%/lov/{date_escaped}"'
                )
            elif doc_type == "REGULATION":
                own_doc_clause = (
                    f'canonical_document_id like "%/forskrift/{date_escaped}"'
                )
            else:
                own_doc_clause = (
                    f'canonical_document_id like "%/{date_escaped}"'
                )
        else:
            own_doc_clause = f'source_url like "%{date_escaped}%"'
        if "document_type" in schema_fields and doc_type in {"LAW", "REGULATION"}:
            own_doc_clause = (
                f'({own_doc_clause} and document_type == "{doc_type}")'
            )

        clauses = [own_doc_clause]
        if (
            include_linked_regulations
            and doc_type == "LAW"
            and "parent_law_canonical_id" in schema_fields
        ):
            clauses.append(
                f'parent_law_canonical_id == "NL/lov/{date_escaped}"'
            )
            clauses.append(
                f'parent_law_canonical_id == "LTI/lov/{date_escaped}"'
            )
            # Handles future/alternate namespaces without enumerating them.
            clauses.append(
                f'parent_law_canonical_id like "%/lov/{date_escaped}"'
            )

        if len(clauses) == 1:
            return clauses[0]
        return f"({' or '.join(clauses)})"

    @classmethod
    def source_doc_url_expr(
        cls,
        statute_filter: Optional[str],
        schema_fields: Optional[Set[str]] = None,
        include_linked_regulations: bool = True,
    ) -> str:
        schema = schema_fields or set()
        tokens = cls._split_statute_filters(statute_filter)
        expressions: List[str] = []
        seen: Set[str] = set()

        for token in tokens:
            expr = cls._single_statute_expr(
                token,
                schema,
                include_linked_regulations=include_linked_regulations,
            )
            if expr and expr not in seen:
                seen.add(expr)
                expressions.append(expr)

        if not expressions:
            return ""
        if len(expressions) == 1:
            return expressions[0]
        return f"({' or '.join(expressions)})"

    @classmethod
    def _required_source_tokens(
        cls,
        subdomain_candidates: Optional[Sequence[str]],
    ) -> List[str]:
        """Read required source IDs from taxonomy while preserving source type."""
        if not subdomain_candidates:
            return []

        from router.taxonomy_loader import taxonomy_loader

        tokens: List[str] = []
        seen: Set[str] = set()
        for sub_id in subdomain_candidates:
            sub_data = taxonomy_loader.get_subdomain(sub_id)
            if not sub_data:
                continue
            for src in sub_data.get("required_sources", []):
                source_id = src.get("source_id")
                if source_id and source_id not in seen:
                    seen.add(source_id)
                    tokens.append(source_id)
        return tokens

    @classmethod
    def _domain_expr(cls, schema_fields: Set[str], domain: Optional[str]) -> str:
        if not domain:
            return ""

        raw = str(domain).strip()
        canonical = raw.lower()

        if "domain_id" in schema_fields:
            if re.match(r"^D\d+_", raw, re.IGNORECASE):
                domain_id = raw.upper()
            else:
                domain_id = _DOMAIN_CANONICAL_TO_ID.get(canonical)
            if domain_id:
                return f'domain_id == "{cls._escape(domain_id)}"'

        if "domain_name" in schema_fields:
            domain_name = _DOMAIN_CANONICAL_TO_NAME.get(canonical, raw)
            return f'domain_name == "{cls._escape(domain_name)}"'

        if "domain" in schema_fields:
            return f'domain == "{cls._escape(raw)}"'

        return ""

    @classmethod
    def build_expr(
        cls,
        schema_fields: Set[str],
        statute_filter: Optional[str],
        domain: Optional[str],
        jurisdiction: Optional[str],
        subdomain_candidates: Optional[List[str]] = None,
        b2b_b2c: Optional[str] = None,
        level: int = 0,
        exact_statute_only: bool = False,
    ) -> Optional[str]:
        
        if level not in {0, 1, 2, 3, 4}:
            raise ValueError(f"Unsupported Milvus fallback level: {level}")

        parts: List[str] = []

        # Statute/source restrictions for L0-L2.
        if level in {0, 1, 2} and statute_filter:
            source_tokens = cls._split_statute_filters(statute_filter)

            # Preserve existing taxonomy-required-source behavior for routed
            # searches, but add each source as its actual type instead of opening
            # the filter to all regulations.
            if subdomain_candidates and not exact_statute_only:
                existing_dates = {
                    parsed[0]
                    for parsed in (cls._parse_statute_token(t) for t in source_tokens)
                    if parsed[0]
                }
                for required_id in cls._required_source_tokens(subdomain_candidates):
                    required_date, _ = cls._parse_statute_token(required_id)
                    if required_date and required_date not in existing_dates:
                        source_tokens.append(required_id)
                        existing_dates.add(required_date)

            source_expr = cls.source_doc_url_expr(
                ",".join(source_tokens),
                schema_fields,
                include_linked_regulations=not exact_statute_only,
            )
            if source_expr:
                parts.append(source_expr)

        # Domain restrictions for L0, L1, L3, L4.
        if level in {0, 1, 3, 4}:
            domain_expr = cls._domain_expr(schema_fields, domain)
            if domain_expr:
                parts.append(domain_expr)

        # Subdomain restrictions for tight/domain fallback levels.
        if (
            level in {0, 3}
            and subdomain_candidates
            and "subdomain_id" in schema_fields
        ):
            unique_subs = list(dict.fromkeys(str(s) for s in subdomain_candidates if s))
            if len(unique_subs) == 1:
                parts.append(
                    f'subdomain_id == "{cls._escape(unique_subs[0])}"'
                )
            elif unique_subs:
                subs_formatted = ", ".join(
                    f'"{cls._escape(s)}"' for s in unique_subs
                )
                parts.append(f"subdomain_id in [{subs_formatted}]")
        if level in {0, 3} and jurisdiction and "jurisdiction" in schema_fields:
            j_val = str(jurisdiction).upper()
            if j_val != "BOTH":
                parts.append(
                    f'(jurisdiction == "{cls._escape(j_val)}" or jurisdiction == "BOTH")'
                )

        # B2B/B2C is intentionally only used on L0/L3.
        if level in {0, 3} and b2b_b2c and "b2b_b2c" in schema_fields:
            b_val = str(b2b_b2c).upper()
            if b_val == "SMB":
                b_val = "B2B"
            elif b_val == "CONSUMER":
                b_val = "B2C"
            if b_val in {"B2B", "B2C"}:
                parts.append(
                    f'(b2b_b2c == "{b_val}" or b2b_b2c == "BOTH")'
                )

        if "retrieval_enabled" in schema_fields:
            parts.append("retrieval_enabled == True")

        return " and ".join(parts) if parts else None


class MilvusClient:
    _instance: Optional["MilvusClient"] = None

    def __new__(cls) -> "MilvusClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_ready"):
            self.host: Optional[str] = None
            self.port: Optional[int] = None
            self.collection_name: Optional[str] = None
            self.alias: str = "default"
            self._collection: Optional[Collection] = None
            self._schema_fields: Set[str] = set()
            self._ready = False

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=2))
    def connect(
        self,
        host: str,
        port: int,
        collection_name: str,
        alias: str = "default",
    ) -> None:
        try:
            logger.info("Connecting to Milvus at %s:%s (alias=%s)...", host, port, alias)

            self.host = host
            self.port = port
            self.collection_name = collection_name
            self.alias = alias

            connections.connect(alias=alias, host=host, port=port)

            if not utility.has_collection(collection_name):
                raise ValueError(
                    f"Collection '{collection_name}' does not exist in Milvus."
                )

            self._collection = Collection(collection_name)
            self._collection.load()

            # Introspect real schema — prevents output/filter field errors.
            self._schema_fields = {f.name for f in self._collection.schema.fields}

            self._ready = True
            logger.info(
                "[OK] Milvus connected | collection='%s' | entities=%s",
                collection_name,
                f"{self._collection.num_entities:,}",
            )
            logger.info("Schema fields: %s", sorted(self._schema_fields))

        except Exception as exc:
            logger.error("[ERROR] Milvus connection failed | %s", exc, exc_info=True)
            raise ConnectionError(f"Milvus connection failed: {exc}") from exc

    def check_connection(self) -> bool:
        try:
            if not self._ready or self._collection is None:
                return False
            _ = self._collection.num_entities
            return True
        except Exception as exc:
            logger.error("Milvus health check failed: %s", exc)
            return False

    def close(self) -> None:
        """Release the collection and disconnect."""
        try:
            if self._collection:
                self._collection.release()
                logger.info("Released Milvus collection '%s'", self.collection_name)
            connections.disconnect(self.alias or "default")
            self._ready = False
            self._collection = None
            logger.info("Milvus disconnected")
        except Exception as exc:
            logger.error("Error closing Milvus: %s", exc)

    def _ensure_loaded(self) -> None:
        """Ensure the collection is loaded in memory."""
        if self.collection_name is None or self._collection is None:
            return
        load_state = utility.load_state(self.collection_name)
        if load_state.name != "Loaded":
            logger.warning(
                "Collection '%s' not in memory. Reloading...",
                self.collection_name,
            )
            self._collection.load()

    def _has(self, field: str) -> bool:
        return field in self._schema_fields

    def _source_doc_url_expr(self, statute_filter: Optional[str]) -> str:
        return MilvusFilterBuilder.source_doc_url_expr(
            statute_filter, self._schema_fields
        )

    def _build_expr(
        self,
        statute_filter: Optional[str],
        domain: Optional[str],
        jurisdiction: Optional[str],
        subdomain_candidates: Optional[List[str]] = None,
        b2b_b2c: Optional[str] = None,
        level: int = 0,
        exact_statute_only: bool = False,
    ) -> Optional[str]:
        return MilvusFilterBuilder.build_expr(
            schema_fields=self._schema_fields,
            statute_filter=statute_filter,
            domain=domain,
            jurisdiction=jurisdiction,
            subdomain_candidates=subdomain_candidates,
            b2b_b2c=b2b_b2c,
            level=level,
            exact_statute_only=exact_statute_only,
        )

    _DESIRED_OUTPUT_FIELDS = [
        "chunk_id",
        "canonical_document_id",
        "legal_document_id",
        "legal_section_id",
        "source_section_key",
        "source_url",
        "document_type",
        "doc_title",
        "section_number",
        "section_title",
        "citation_anchor",
        "domain_id",
        "domain_name",
        "subdomain_id",
        "subdomain_name",
        "taxonomy_version",
        "parent_law_canonical_id",
        "parent_law_title",
        "jurisdiction",
        "b2b_b2c",
        "relationship_type",
        "source_type",
        "tier",
        "language",
        "version_date",
        "content_hash",
        "is_current",
        "retrieval_enabled",
        "text",
    ]

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=2))
    def search(
        self,
        embedding: List[float],
        metric_type: str = "COSINE",
        top_k: int = 50,
        min_score: float = 0.0,
        output_fields: Optional[List[str]] = None,
        statute_filter: Optional[str] = None,
        domain: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        subdomain_candidates: Optional[List[str]] = None,
        b2b_b2c: Optional[str] = None,
        fallback_level: int = 0,
        source_type: Optional[str] = None,
        exact_statute_only: bool = False,
    ) -> List[Dict[str, Any]]:
        if not self._ready or self._collection is None:
            raise RuntimeError(
                "Milvus collection not initialized. Call connect() first."
            )
        self._ensure_loaded()

        if output_fields is None:
            output_fields = [
                field for field in self._DESIRED_OUTPUT_FIELDS if self._has(field)
            ]
        else:
            output_fields = [field for field in output_fields if self._has(field)]

        expr = self._build_expr(
            statute_filter=statute_filter,
            domain=domain,
            jurisdiction=jurisdiction,
            subdomain_candidates=subdomain_candidates,
            b2b_b2c=b2b_b2c,
            level=fallback_level,
            exact_statute_only=exact_statute_only,
        )

        logger.info(
            "Milvus search | level=L%s | expr=%r | top_k=%s",
            fallback_level,
            expr,
            top_k,
        )

        from config import settings

        metric_type = getattr(settings, "MILVUS_METRIC_TYPE", None) or metric_type or "COSINE"
        index_type = "HNSW"
        try:
            if self._collection and self._collection.indexes:
                index_type = (
                    self._collection.indexes[0].params.get("index_type") or "HNSW"
                ).upper()
                logger.debug("Dynamically detected Milvus index type: %s", index_type)
        except Exception as exc:
            logger.warning("Failed to detect index type: %s", exc)

        search_p: Dict[str, Any] = {"metric_type": metric_type, "params": {}}
        if "HNSW" in index_type:
            search_p["params"]["ef"] = 256
        elif "IVF" in index_type:
            search_p["params"]["nprobe"] = 128
        else:
            search_p["params"]["nprobe"] = 128
            search_p["params"]["ef"] = 256

        try:
            results = self._collection.search(
                data=[embedding],
                anns_field="embedding",
                param=search_p,
                limit=top_k,
                output_fields=output_fields,
                expr=expr,
            )

            hits: List[Dict[str, Any]] = []
            for batch in results:
                for hit in batch:
                    score = float(hit.distance)
                    row: Dict[str, Any] = {"score": score}

                    for field in output_fields:
                        value = getattr(hit.entity, field, None)
                        if value is None and hasattr(hit.entity, "get"):
                            value = hit.entity.get(field)
                        row[field] = value

                    # Backwards-compatibility aliases for the existing RAG pipeline.
                    row["url"] = row.get("source_url")
                    row["source_doc_url"] = row.get("source_url")
                    row["file_name"] = row.get("source_url")
                    row["document_id"] = (
                        row.get("canonical_document_id")
                        or row.get("source_section_key")
                    )
                    row["section_ref"] = (
                        row.get("section_number") or row.get("citation_anchor")
                    )
                    row["domain"] = row.get("domain_name") or row.get("domain_id")
                    row["subdomain"] = (
                        row.get("subdomain_name") or row.get("subdomain_id")
                    )
                    row["law_title"] = row.get("doc_title")

                    hits.append(row)

            logger.info(
                "Milvus returned %s/%s hits | level=L%s",
                len(hits),
                top_k,
                fallback_level,
            )
            return hits

        except Exception as exc:
            logger.error("Milvus search failed | %s", exc, exc_info=True)
            raise ValueError(f"Milvus search failed: {exc}") from exc

    def get_stats(self) -> Dict[str, Any]:
        """Return basic collection statistics for the health endpoint."""
        if not self._ready or self._collection is None:
            return {"status": "not_initialized"}
        try:
            return {
                "status": "connected",
                "collection_name": self.collection_name,
                "num_entities": self._collection.num_entities,
                "host": self.host,
                "port": self.port,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}


milvus_client = MilvusClient()


def get_milvus() -> MilvusClient:
    """Return the singleton MilvusClient (for dependency injection in main.py)."""
    return milvus_client
