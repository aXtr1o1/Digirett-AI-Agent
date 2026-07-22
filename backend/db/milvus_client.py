"""
db/milvus_client.py

Milvus vector database client — singleton.

Updated for new Milvus schema (DigiRett v3):
  Fields: milvus_id, chunk_id, document_id, source_doc_url, section_ref,
          domain, subdomain, b2b_b2c, tier, jurisdiction, text, embedding

Key changes from Phase 1:
  - output_fields updated to match new schema
  - statute filter now uses source_doc_url LIKE expression (not statute_id ==)
  - domain filter uses `domain` field (not `domain_name`)
  - url alias → section_ref  (for citation display in chat.py)
  - file_name alias kept for backward-compat with message_service.py
"""

import logging
import re
from typing import Any, Dict, List, Optional

from pymilvus import connections, Collection, utility
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class MilvusClient:
    """
    Thread-safe singleton Milvus client.

    Call connect() once at startup (done in main.py lifespan).
    After that, all agents share the same collection reference.
    """

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
            self._collection: Optional[Collection] = None
            self._schema_fields: set = set()   # populated at connect()
            self._ready = False

    # ── Connection ───────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=2))
    def connect(self, host: str, port: int, collection_name: str) -> None:
        """
        Connect to the Milvus server and load the target collection into memory.
        Introspects the live schema so output_fields are always safe.
        """
        try:
            logger.info(f"Connecting to Milvus at {host}:{port}...")

            self.host = host
            self.port = port
            self.collection_name = collection_name

            connections.connect(alias="default", host=host, port=port)

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
            logger.error(f"❌ Milvus health check failed | {exc}")
            return False

    def close(self) -> None:
        """Release the collection and disconnect."""
        try:
            if self._collection:
                self._collection.release()
                logger.info(
                    f"📤 Released Milvus collection '{self.collection_name}'"
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
                f"⚠️ Collection '{self.collection_name}' not in memory. Reloading..."
            )
            self._collection.load()

    # ── Filter helpers ───────────────────────────────────────────────────

    def _has(self, field: str) -> bool:
        """Return True only if field exists in the live schema."""
        return field in self._schema_fields

    @staticmethod
    def _source_doc_url_expr(statute_filter: Optional[str]) -> str:
        """
        Build a source_doc_url LIKE filter from a Lovdata URL or statute ID.

        statute_filter may be:
          - Full URL:  "https://lovdata.no/lov/1997-06-13-44"
          - Statute ID: "LOV-1997-06-13-44"

        We match on the date+number suffix which uniquely identifies one statute.
        "LOV-1997-06-13-44"  →  date_part = "1997-06-13-44"
        "https://lovdata.no/lov/1997-06-13-44" → date_part = "1997-06-13-44"
        """
        if not statute_filter:
            return ""

        s = statute_filter.strip()

        # Full URL: extract the date-number tail
        if s.startswith("http"):
            date_part = s.rstrip("/").split("/")[-1]
        else:
            # Strip LOV-/FOR-/FORSKRIFT- prefix
            date_part = re.sub(
                r"^(LOV|FOR|FORSKRIFT)-", "", s, flags=re.IGNORECASE
            )

        if not date_part:
            return ""

        return f'source_doc_url like "%{date_part}%"'

    def _build_expr(
        self,
        statute_filter: Optional[str],
        domain: Optional[str],
        jurisdiction: Optional[str],
        subdomain_candidates: Optional[List[str]] = None,
        b2b_b2c: Optional[str] = None,
        level: int = 0,
    ) -> Optional[str]:
        """
        Build a Milvus filter expression for the given fallback level.

        level 0 — source_doc_url + domain + subdomain + jurisdiction + b2b_b2c
        level 1 — source_doc_url + domain
        level 2 — source_doc_url only
        level 3 — no filter (pure vector search)

        Only adds a clause when the field exists in the live schema.
        tier is VarChar — never use numeric comparison on it.
        """
        parts = []

        # Extract subdomain required sources if level < 3
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

        # source_doc_url LIKE filter (levels 0, 1, 2)
        if level < 3 and self._has("source_doc_url"):
            all_dps = []
            if statute_filter:
                for item in statute_filter.split(","):
                    s = item.strip()
                    if not s:
                        continue
                    if s.startswith("http"):
                        dp = s.rstrip("/").split("/")[-1]
                    else:
                        dp = re.sub(r"^(LOV|FOR|FORSKRIFT)-", "", s, flags=re.IGNORECASE)
                    if dp and dp not in all_dps:
                        all_dps.append(dp)

            # Combine primary with subdomain required sources
            for dp in required_date_parts:
                if dp not in all_dps:
                    all_dps.append(dp)

            if all_dps:
                if len(all_dps) == 1:
                    parts.append(f'source_doc_url like "%{all_dps[0]}%"')
                else:
                    or_expr = " or ".join(f'source_doc_url like "%{dp}%"' for dp in all_dps)
                    parts.append(f"({or_expr})")

        # domain (levels 0, 1)
        if level < 2 and domain and self._has("domain"):
            # Bypass strict domain filter at level 0 if we have specific subdomain candidates
            # to allow cross-domain co-retrieval (e.g. CY-06 and IN-04)
            if not (level == 0 and subdomain_candidates):
                safe_domain = domain.replace('"', '\\"')
                parts.append(f'domain == "{safe_domain}"')

        # subdomain candidates (level 0 only)
        if level == 0 and subdomain_candidates:
            subs = [s for s in subdomain_candidates if s]
            if self._has("subdomain_id"):
                # Query subdomain_id field directly using the subdomain IDs
                if len(subs) == 1:
                    safe_sub = subs[0].replace('"', '\\"')
                    parts.append(f'subdomain_id == "{safe_sub}"')
                elif len(subs) > 1:
                    sub_expr = " or ".join(
                        f'subdomain_id == "{s.replace(chr(34), chr(92)+chr(34))}"'
                        for s in subs
                    )
                    parts.append(f"({sub_expr})")
            elif self._has("subdomain"):
                # Fallback: Translate subdomain IDs to English and Norwegian names
                all_sub_names = []
                from router.taxonomy_loader import taxonomy_loader
                for s in subs:
                    all_sub_names.append(s)
                    if re.match(r"^[A-Z]{2}-\d{2}$", s):
                        sub_data = taxonomy_loader.get_subdomain(s)
                        if sub_data:
                            if sub_data.get("name_en"):
                                all_sub_names.append(sub_data.get("name_en"))
                            if sub_data.get("name_nb"):
                                all_sub_names.append(sub_data.get("name_nb"))

                if len(all_sub_names) == 1:
                    safe_sub = all_sub_names[0].replace('"', '\\"')
                    parts.append(f'subdomain == "{safe_sub}"')
                elif len(all_sub_names) > 1:
                    sub_expr = " or ".join(
                        f'subdomain == "{s.replace(chr(34), chr(92)+chr(34))}"'
                        for s in all_sub_names
                    )
                    parts.append(f"({sub_expr})")

        # jurisdiction (level 0 only)
        if level == 0 and jurisdiction and self._has("jurisdiction"):
            j = jurisdiction.upper()
            if j not in ("BOTH", ""):
                safe_j = j.replace('"', '\\"')
                parts.append(
                    f'(jurisdiction == "{safe_j}" or jurisdiction == "BOTH")'
                )

        # b2b_b2c (level 0 only)
        if level == 0 and b2b_b2c and self._has("b2b_b2c"):
            b = b2b_b2c.upper()
            if b not in ("BOTH", ""):
                safe_b = b.replace('"', '\\"')
                parts.append(
                    f'(b2b_b2c == "{safe_b}" or b2b_b2c == "BOTH")'
                )

        if not parts:
            return None

        return " and ".join(parts)

    # ── Search ───────────────────────────────────────────────────────────

    # New schema output fields — only fields that exist are queried (safe via _has)
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
        """
        Search Milvus for nearest neighbours using the 4-level fallback ladder.

        fallback_level controls filter tightness:
          0 — source_doc_url + domain + subdomain + jurisdiction + b2b_b2c
          1 — source_doc_url + domain
          2 — source_doc_url only
          3 — no filter (pure vector search)

        min_score is intentionally NOT applied here — handled downstream by BM25Reranker.
        """
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

                    # ── Aliases for downstream compatibility ─────────────
                    # chat.py reads chunk.get("url") for citation display
                    # section_ref is the human-readable citation anchor
                    # source_doc_url is the full Lovdata URL
                    row["url"] = row.get("source_doc_url")        # citation link
                    row["file_name"] = row.get("source_doc_url")  # backward-compat

                    hits.append(row)

            logger.info(
                f"  Milvus returned {len(hits)}/{top_k} hits | level=L{fallback_level}"
            )
            return hits

        except Exception as exc:
            logger.error(f"❌ Milvus search failed | {exc}", exc_info=True)
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