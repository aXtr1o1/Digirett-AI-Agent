import logging
import re
from typing import Any, Dict, List, Optional

from pymilvus import connections, Collection, utility
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


from pydantic import BaseModel, Field

class MilvusConfig(BaseModel):
    host: str
    port: int
    collection_name: str
    alias: str = Field(default="default")
    timeout: float = Field(default=10.0)


class MilvusFilterBuilder:
    """Standalone builder for Milvus boolean filter expressions."""

    @staticmethod
    def source_doc_url_expr(statute_filter: Optional[str]) -> str:
        if not statute_filter:
            return ""
        s = statute_filter.strip()
        if s.startswith("http"):
            date_part = s.rstrip("/").split("/")[-1]
        else:
            date_part = re.sub(r"^(LOV|FOR|FORSKRIFT)-", "", s, flags=re.IGNORECASE)
        if not date_part:
            return ""
        return f'source_doc_url like "%{date_part}%"'

    @classmethod
    def build_expr(
        cls,
        schema_fields: set,
        statute_filter: Optional[str],
        domain: Optional[str],
        jurisdiction: Optional[str],
        subdomain_candidates: Optional[List[str]] = None,
        b2b_b2c: Optional[str] = None,
        level: int = 0,
    ) -> Optional[str]:
        parts = []
        required_date_parts = []
        if level < 3 and subdomain_candidates:
            from router.taxonomy_loader import taxonomy_loader
            for sub_id in subdomain_candidates:
                sub_data = taxonomy_loader.get_subdomain(sub_id)
                if sub_data:
                    for src in sub_data.get("required_sources", []):
                        sid = src.get("source_id")
                        if sid:
                            dp = re.sub(r"^(LOV|FOR|FORSKRIFT)-", "", sid, flags=re.IGNORECASE)
                            if dp and dp not in required_date_parts:
                                required_date_parts.append(dp)

        # 1. Primary statute filter
        if level <= 2 and statute_filter:
            primary_expr = cls.source_doc_url_expr(statute_filter)
            if primary_expr:
                if level < 3 and required_date_parts:
                    or_clauses = [primary_expr]
                    for dp in required_date_parts:
                        or_clauses.append(f'source_doc_url like "%{dp}%"')
                    parts.append(f"({' or '.join(or_clauses)})")
                else:
                    parts.append(primary_expr)
        elif level < 3 and required_date_parts:
            or_clauses = [f'source_doc_url like "%{dp}%"' for dp in required_date_parts]
            parts.append(f"({' or '.join(or_clauses)})")

        if level == 3 or not parts:
            if level <= 1 and domain and "domain" in schema_fields:
                parts.append(f'domain == "{domain}"')

        # 2. Subdomain filter
        if level == 0 and subdomain_candidates and "subdomain_id" in schema_fields:
            if len(subdomain_candidates) == 1:
                parts.append(f'subdomain_id == "{subdomain_candidates[0]}"')
            else:
                subs_formatted = ", ".join(f'"{s}"' for s in subdomain_candidates)
                parts.append(f"subdomain_id in [{subs_formatted}]")

        # 3. Jurisdiction filter
        if level <= 1 and "jurisdiction" in schema_fields:
            if jurisdiction and jurisdiction.upper() != "BOTH":
                j_val = jurisdiction.upper()
                parts.append(f'(jurisdiction == "{j_val}" or jurisdiction == "BOTH")')

        # 4. B2B / B2C filter
        if level == 0 and b2b_b2c and "b2b_b2c" in schema_fields:
            b_val = b2b_b2c.upper()
            if b_val != "BOTH":
                parts.append(f'(b2b_b2c == "{b_val}" or b2b_b2c == "BOTH")')

        if not parts:
            return None
        return " and ".join(parts)


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
            self._schema_fields: set = set()   # populated at connect()
            self._ready = False

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=2))
    def connect(self, host: str, port: int, collection_name: str, alias: str = "default") -> None:
        
        try:
            logger.info(f"Connecting to Milvus at {host}:{port} (alias={alias})...")

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

            # Introspect real schema — prevents KeyError on missing fields
            self._schema_fields = {
                f.name for f in self._collection.schema.fields
            }

            self._ready = True
            logger.info(
                f"[OK] Milvus connected | collection='{collection_name}' | "
                f"entities={self._collection.num_entities:,}"
            )
            logger.info(f"  Schema fields: {sorted(self._schema_fields)}")

        except Exception as exc:
            logger.error(f"[ERROR] Milvus connection failed | {exc}", exc_info=True)
            raise ConnectionError(f"Milvus connection failed: {exc}") from exc

    def check_connection(self) -> bool:
        """Ping Milvus by fetching entity count. Returns True when healthy."""
        try:
            if not self._ready or self._collection is None:
                return False
            _ = self._collection.num_entities
            return True
        except Exception as exc:
            logger.error(f" Milvus health check failed | {exc}")
            return False

    def close(self) -> None:
        """Release the collection and disconnect."""
        try:
            if self._collection:
                self._collection.release()
                logger.info(
                    f" Released Milvus collection '{self.collection_name}'"
                )
            connections.disconnect("default")
            self._ready = False
            self._collection = None
            logger.info("🔌 Milvus disconnected")
        except Exception as exc:
            logger.error(f"Error closing Milvus: {exc}")

    def _ensure_loaded(self) -> None:
        """Ensure the collection is loaded in memory."""
        if self.collection_name is None or self._collection is None:
            return
        load_state = utility.load_state(self.collection_name)
        if load_state.name != "Loaded":
            logger.warning(
                f" Collection '{self.collection_name}' not in memory. Reloading..."
            )
            self._collection.load()

    def _has(self, field: str) -> bool:
        """Return True only if field exists in the live schema."""
        return field in self._schema_fields

    def _source_doc_url_expr(self, statute_filter: Optional[str]) -> str:
        return MilvusFilterBuilder.source_doc_url_expr(statute_filter)

    def _build_expr(
        self,
        statute_filter: Optional[str],
        domain: Optional[str],
        jurisdiction: Optional[str],
        subdomain_candidates: Optional[List[str]] = None,
        b2b_b2c: Optional[str] = None,
        level: int = 0,
    ) -> Optional[str]:
        return MilvusFilterBuilder.build_expr(
            schema_fields=self._schema_fields,
            statute_filter=statute_filter,
            domain=domain,
            jurisdiction=jurisdiction,
            subdomain_candidates=subdomain_candidates,
            b2b_b2c=b2b_b2c,
            level=level,
        )

        if not parts:
            return None

        return " and ".join(parts)

    _DESIRED_OUTPUT_FIELDS = [
        "chunk_id",
        "document_id",
        "source_doc_url",
        "section_ref",
        "domain",
        "subdomain",
        "subdomain_id",
        "b2b_b2c",
        "tier",
        "jurisdiction",
        "text",
    ]

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=2))
    def search(
        self,
        embedding: List[float],
        metric_type: str = "COSINE",
        top_k: int = 50,
        min_score: float = 0.0,          # kept — not used for filtering (reranker handles it)
        output_fields: Optional[List[str]] = None,
        statute_filter: Optional[str] = None,    # Lovdata URL or LOV-YYYY-MM-DD-NNN
        domain: Optional[str] = None,            # e.g. "selskapsrett"
        jurisdiction: Optional[str] = None,      # e.g. "NO"
        subdomain_candidates: Optional[List[str]] = None,
        b2b_b2c: Optional[str] = None,
        fallback_level: int = 0,                 # 0=tight, 1=domain, 2=statute, 3=none
        source_type: Optional[str] = None,       # not filtered — not stored consistently
    ) -> List[Dict[str, Any]]:
        if not self._ready or self._collection is None:
            raise RuntimeError(
                "Milvus collection not initialized. Call connect() first."
            )
        self._ensure_loaded()

        # Build safe output_fields from live schema
        if output_fields is None:
            output_fields = [
                f for f in self._DESIRED_OUTPUT_FIELDS
                if self._has(f)
            ]

        # Build filter expression for this fallback level
        expr = self._build_expr(
            statute_filter=statute_filter,
            domain=domain,
            jurisdiction=jurisdiction,
            subdomain_candidates=subdomain_candidates,
            b2b_b2c=b2b_b2c,
            level=fallback_level,
        )

        logger.info(
            f"🔍 Milvus search | level=L{fallback_level} | expr={expr!r} | top_k={top_k}"
        )

        # Detect index type dynamically from the collection indexes
        from config import settings
        metric_type = getattr(settings, "MILVUS_METRIC_TYPE", None) or "COSINE"
        index_type = "HNSW"
        try:
            if self._collection and self._collection.indexes:
                index_type = (self._collection.indexes[0].params.get("index_type") or "HNSW").upper()
                logger.debug(f"Dynamically detected Milvus index type: {index_type}")
        except Exception as e:
            logger.warning(f"Failed to detect index type: {e}")
            
        search_p = {"metric_type": metric_type, "params": {}}
        if "HNSW" in index_type:
            search_p["params"]["ef"] = 256
        elif "IVF" in index_type:
            search_p["params"]["nprobe"] = 128
        else:
            # Safe fallback defaults
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

            hits = []
            for batch in results:
                for hit in batch:
                    score = float(hit.distance)
                    row: Dict[str, Any] = {"score": score}

                    for field in output_fields:
                        value = getattr(hit.entity, field, None)
                        if value is None and hasattr(hit.entity, "get"):
                            value = hit.entity.get(field)
                        row[field] = value
                    row["url"] = row.get("source_doc_url")        # citation link
                    row["file_name"] = row.get("source_doc_url")  # backward-compat

                    hits.append(row)

            logger.info(
                f"  Milvus returned {len(hits)}/{top_k} hits | level=L{fallback_level}"
            )
            return hits

        except Exception as exc:
            logger.error(f" Milvus search failed | {exc}", exc_info=True)
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


# Module-level singleton and DI factory
milvus_client = MilvusClient()


def get_milvus() -> MilvusClient:
    """Return the singleton MilvusClient (for dependency injection in main.py)."""
    return milvus_client