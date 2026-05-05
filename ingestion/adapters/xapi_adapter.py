"""
adapters/xapi_adapter.py
=========================
Adapter for XAPI Lovdata data source.

Mirrors the domain-by-domain collection logic from xapi_lovdata_collector.py:
  - If input_path is a domain key (e.g. "arbeidsrett") -> fetch that domain only
  - If input_path is None -> fetch ALL domains from XAPI_DOMAIN_CONFIG sequentially

For each domain, iterates xapi_rettsomrader values and calls
fetch_all_law_metadata(rettsomrade=...) with pagination -- same as the old collector.
Deduplication within a run is done by dok_id.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from dotenv import load_dotenv

from ingestion.adapters.base_adapter import BaseAdapter
from ingestion.collectors.xapi_collector import XAPIClient
from ingestion.domain_classification.domain_classifier import (
    get_domain_config,
    get_all_domain_keys,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate-limit retry helper
# ---------------------------------------------------------------------------

def _fetch_with_backoff(
    fn,
    *args,
    max_attempts: int = 3,
    base_delay: float = 5.0,
    **kwargs,
) -> Tuple[Any, bool]:
    """
    Call fn(*args, **kwargs) with exponential backoff on HTTP 429.

    Returns:
        (result, True)   -- success
        (None,  False)   -- all retries exhausted (caller should stop batch)
        (None,  None)    -- non-429 HTTP error (caller should skip this record)
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs), True
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                wait = base_delay * (2 ** (attempt - 1))   # 5s -> 10s -> 20s
                if attempt < max_attempts:
                    logger.warning(
                        "XAPI 429 -- attempt %s/%s, backing off %.1fs",
                        attempt, max_attempts, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "XAPI 429 -- all %s retry attempts exhausted. Stopping batch.",
                        max_attempts,
                    )
                    return None, False
            else:
                logger.error("XAPI HTTP error (non-429): %s", exc)
                return None, None   # skip this record
    return None, False


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class XAPIAdapter(BaseAdapter):
    """
    XAPI Lovdata Adapter.

    Fetches laws and regulations domain-by-domain using XAPI_DOMAIN_CONFIG,
    matching the behaviour of the legacy xapi_lovdata_collector.py.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        load_dotenv()

        self.api_key = os.environ.get(self.config.get("api_key_env", "XAPI_KEY"), "").strip()
        if not self.api_key:
            logger.warning("XAPIAdapter: XAPI_KEY not set -- requests will fail.")

        # Rate-limit settings: env -> config -> hard defaults
        self.request_delay = float(
            os.environ.get("XAPI_REQUEST_DELAY_SECONDS",
                           str(self.config.get("request_delay_seconds", 0.8)))
        )
        self.max_retry_attempts = int(
            os.environ.get("XAPI_RETRY_MAX_ATTEMPTS",
                           str(self.config.get("max_retry_attempts", 3)))
        )
        self.retry_base_delay = float(
            os.environ.get("XAPI_RETRY_BASE_SECONDS",
                           str(self.config.get("retry_base_seconds", 5.0)))
        )
        self.page_size = int(
            os.environ.get("XAPI_PAGE_SIZE",
                           str(self.config.get("page_size", 200)))
        )

        try:
            self.client = XAPIClient()
            logger.info(
                "XAPIAdapter: Initialized | delay=%.1fs | retries=%s | retry_base=%.1fs | page_size=%s",
                self.request_delay, self.max_retry_attempts, self.retry_base_delay, self.page_size,
            )
        except Exception as exc:
            logger.error("XAPIAdapter: Failed to init XAPIClient: %s", exc)
            self.client = None

    # -----------------------------------------------------------------------
    def get_source_name(self) -> str:
        return "xapi"

    # -----------------------------------------------------------------------
    def fetch(self, input_path: Optional[str] = None) -> Any:
        """
        Fetch laws/regulations from XAPI, domain-by-domain.

        input_path:
          - A domain key from XAPI_DOMAIN_CONFIG (e.g. "arbeidsrett")
            -> fetches only that domain
          - None -> fetches ALL domains sequentially

        For each domain, iterates its xapi_rettsomrader and calls
        fetch_all_law_metadata(rettsomrade=...) with full pagination.
        """
        if not self.client:
            logger.error("XAPIAdapter: Client not initialised -- skipping.")
            return []

        # Determine which domains to process
        max_docs = self.config.get("fetch_limit")
        all_domain_keys = get_all_domain_keys()

        if input_path and input_path in all_domain_keys:
            domains_to_run = {input_path: get_domain_config(input_path)}
            logger.info("XAPIAdapter: Single domain mode -- domain=%s", input_path)

        elif input_path:
            logger.error(
                "XAPIAdapter: '%s' is not a valid domain key. Valid keys: %s",
                input_path,
                all_domain_keys,
            )
            return []

        else:
            domains_to_run = {
                key: get_domain_config(key)
                for key in all_domain_keys
            }
            logger.info("XAPIAdapter: All-domains mode -- %s domains", len(domains_to_run))

        seen_dok_ids: Set[str] = set()   # cross-domain deduplication
        all_raw_records: List[Dict[str, Any]] = []

        for domain_key, domain_cfg in domains_to_run.items():
            rettsomrader = domain_cfg.get("xapi_rettsomrader", [])

            if not rettsomrader:
                logger.warning(
                    "XAPIAdapter: Domain '%s' has no xapi_rettsomrader -- skipping.",
                    domain_key,
                )
                continue

            logger.info(
                "  [DOMAIN] %s | rettsomrader=%s",
                domain_key, rettsomrader,
            )

            domain_records: List[Dict[str, Any]] = []

            for rettsomrade in rettsomrader:
                logger.info(
                    "    [FETCH] rettsomrade='%s' ...", rettsomrade,
                )

                # Paginated metadata fetch (mirrors fetch_all_law_metadata)
                try:
                    total = self.client.get_law_count(rettsomrade=rettsomrade)
                    logger.info(
                        "    [FETCH] rettsomrade='%s' | total=%s records",
                        rettsomrade, total,
                    )
                except Exception as exc:
                    logger.error(
                        "    [FETCH] get_law_count failed | rettsomrade='%s' | error=%s",
                        rettsomrade, exc,
                    )
                    continue

                offset = 0
                while offset < total:
                    try:
                        page = self.client.fetch_law_metadata_page(
                            limit=self.page_size,
                            offset=offset,
                            rettsomrade=rettsomrade,
                        )
                    except Exception as exc:
                        logger.error(
                            "    [FETCH] metadata page failed | offset=%s | error=%s",
                            offset, exc,
                        )
                        break

                    if not page:
                        break

                    logger.info(
                        "    [FETCH] page | rettsomrade='%s' | offset=%s/%s | got=%s",
                        rettsomrade, offset, total, len(page),
                    )

                    for meta in page:
                        dok_id = meta.get("dok_id", "")
                        xapi_id = meta.get("id")

                        if not dok_id or not xapi_id:
                            continue

                        # Cross-domain dedup (same as old collector)
                        if dok_id in seen_dok_ids:
                            logger.info(
                                "    [DEDUP] Skipping duplicate | dok_id=%s", dok_id
                            )
                            continue
                        seen_dok_ids.add(dok_id)

                        # Step 1 & 2: Supabase Storage Logic
                        from ingestion.collectors.xapi_collector import (
                            SupabaseXAPIStore, build_law_json, build_metadata_payload,
                            build_storage_path,
                        )
                        import json as _json

                        store = SupabaseXAPIStore()
                        existing_row = store.get_existing_row(dok_id)
                        
                        # Only fetch and store if new, refresh, or requested via config
                        is_refresh = self.config.get("refresh", False)
                        if not existing_row or existing_row.get("fetch_status") != "completed" or is_refresh:
                            logger.info(
                                "    [DOC] Fetching detail | dok_id=%-30s | xapi_id=%s",
                                dok_id, xapi_id,
                            )

                            # Fetch detail
                            detail, ok = _fetch_with_backoff(
                                self.client.fetch_law_detail,
                                xapi_id,
                                max_attempts=self.max_retry_attempts,
                                base_delay=self.retry_base_delay,
                            )
                            if ok is False:
                                logger.warning(
                                    "    [ABORT] Rate limit exhausted -- stopping batch."
                                )
                                return all_raw_records
                            if ok is None: continue

                            time.sleep(self.request_delay)

                            # Fetch paragraphs
                            paragraphs, ok = _fetch_with_backoff(
                                self.client.fetch_paragraphs,
                                xapi_id,
                                max_attempts=self.max_retry_attempts,
                                base_delay=self.retry_base_delay,
                            )
                            if ok is False:
                                logger.warning(
                                    "    [ABORT] Rate limit exhausted -- stopping batch."
                                )
                                return all_raw_records
                            if ok is None: continue

                            time.sleep(self.request_delay)

                            # Build and Store
                            law_json = build_law_json(
                                domain_name=domain_key,
                                xapi_filter_type="rettsomrade",
                                xapi_filter_value=rettsomrade,
                                document_type="law", # default
                                law_meta=meta,
                                law_detail=detail,
                                paragraphs_raw=paragraphs
                            )
                            
                            json_bytes = _json.dumps(law_json, ensure_ascii=False, indent=2).encode("utf-8")
                            storage_path = build_storage_path(dok_id)

                            # 1. Upload to bucket
                            store.upload_json_file(storage_path, json_bytes)

                            # 2. Upsert metadata
                            meta_payload = build_metadata_payload(
                                domain_name=domain_key,
                                document_type="law",
                                law=meta,
                                law_detail=detail,
                                paragraph_count=len(paragraphs)
                            )
                            store.upsert_metadata(meta_payload)
                        else:
                            logger.info("    [SKIP] Already completed in Supabase | dok_id=%s", dok_id)
                            # Append domain if needed
                            store.append_domain_name(dok_id, domain_key)
                            # We still need the full item for the rest of the pipeline
                            # but we can fetch it from bucket later or return meta
                            # For the adapter return, we'll provide the minimal meta to trigger the next stages
                            detail = existing_row.get("raw_metadata", {})
                            paragraphs = [] # Will be downloaded in Stage 2

                        domain_records.append({
                            "metadata": meta,
                            "detail": detail or {},
                            "paragraphs": paragraphs or [],
                            "domain_name": domain_key,
                        })

                        # Check max_docs limit after appending
                        if max_docs and (len(all_raw_records) + len(domain_records)) >= max_docs:
                            logger.info("    [LIMIT] Reached max_docs=%s limit.", max_docs)
                            return all_raw_records + domain_records

                    offset += self.page_size
                    time.sleep(0.2)  # polite page delay

            logger.info(
                "  [DOMAIN] %s | collected %s records",
                domain_key, len(domain_records),
            )
            all_raw_records.extend(domain_records)

        logger.info("XAPIAdapter: Total records fetched: %s", len(all_raw_records))
        return all_raw_records

    # -----------------------------------------------------------------------
    def parse(self, raw_data: Any) -> List[Dict[str, Any]]:
        """
        Map XAPI JSON records to the raw-dict format expected by FormatNormaliser.
        The domain_name is passed through so the classifier can use it directly.
        """
        records: List[Dict[str, Any]] = []
        if not raw_data or not isinstance(raw_data, list):
            return records

        for item in raw_data:
            meta      = item.get("metadata", {})
            detail    = item.get("detail", {})
            paragraphs = item.get("paragraphs", [])
            domain_name = item.get("domain_name", "")

            text_content = "\n\n".join(
                p.get("innhold_text", "")
                for p in paragraphs
                if p.get("innhold_text")
            )

            dok_id = meta.get("dok_id", "")
            records.append({
                "source_id":     dok_id,
                "title":         meta.get("tittel"),
                "content":       text_content,
                "raw_json":      item,
                "domain":        domain_name,   # pre-set domain -- skips classifier
                "source_doc_url": (
                    f"https://lovdata.no/dokument/{dok_id}" if dok_id else ""
                ),
                "metadata": {
                    "department":   meta.get("departement"),
                    "rettsomrade":  meta.get("rettsomrade"),
                    "dato":         detail.get("dato_ikraft") or meta.get("dato"),
                },
            })

        return records
