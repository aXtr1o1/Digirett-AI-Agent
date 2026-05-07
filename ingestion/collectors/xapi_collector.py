from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import requests
from dotenv import load_dotenv
from supabase import Client, create_client

from ingestion.domain_classification.domain_classifier import (
    get_domain_config,
    get_all_domain_keys,
)
load_dotenv()

XAPI_BASE_URL: str = os.environ.get("XAPI_BASE_URL", "https://xapi.no").rstrip("/")
XAPI_API_KEY: str = os.environ.get("XAPI_KEY", "").strip()
SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY: str = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
SUPABASE_XAPI_BUCKET: str = os.environ.get("SUPABASE_XAPI_BUCKET", "raw_json_files").strip()
XAPI_METADATA_TABLE: str = os.environ.get("SUPABASE_XAPI_TABLE", "xapi_lovdata_metadata").strip()

XAPI_PAGE_SIZE: int = int(os.environ.get("XAPI_PAGE_SIZE", "200"))

XAPI_TYPE_PARAM: Dict[str, str] = {
    "law": "lov",
    "regulation": "forskrift",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger("xapi_lovdata_collector")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_env() -> None:
    missing = []
    if not XAPI_API_KEY:
        missing.append("XAPI_KEY")
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_KEY")
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )


# ---------------------------------------------------------------------------
# URL / ID helpers
# ---------------------------------------------------------------------------


def build_source_id(dok_id: str) -> str:
    if dok_id.startswith("NL/lov/"):
        return dok_id.replace("NL/lov/", "LOV-")
    if dok_id.startswith("SF/forskrift/"):
        return dok_id.replace("SF/forskrift/", "FORSKRIFT-")
    if dok_id.startswith("NL/forskrift/"):
        return dok_id.replace("NL/forskrift/", "FORSKRIFT-")
    return dok_id.replace("/", "-").upper()


def build_lovdata_source_url(
    dok_id: Optional[str] = None,
    ref_id: Optional[str] = None,
) -> Optional[str]:
    for raw in (dok_id, ref_id):
        if not raw:
            continue
        clean = raw.strip()
        if clean.startswith(("NL/", "SF/", "LTI/")):
            return f"https://lovdata.no/dokument/{clean}"
        if clean.startswith("lov/"):
            return f"https://lovdata.no/dokument/NL/{clean}"
        if clean.startswith("forskrift/"):
            return f"https://lovdata.no/dokument/SF/{clean}"
    return None


def build_file_name(dok_id: str) -> str:
    return dok_id.replace("NL/", "").replace("SF/", "").replace("/", "-") + ".json"


def build_storage_path(dok_id: str) -> str:
    file_name = build_file_name(dok_id)
    if "lov-" in file_name and "forskrift" not in file_name:
        return f"xapi_lovdata/laws/{file_name}"
    return f"xapi_lovdata/regulations/{file_name}"


def build_xapi_doc_url(xapi_id: int) -> str:
    return f"{XAPI_BASE_URL}/v1/lovdata/lover/{xapi_id}"


# ---------------------------------------------------------------------------
# XAPI HTTP client
# ---------------------------------------------------------------------------


class XAPIClient:
    """Thin HTTP wrapper for XAPI Lovdata endpoints."""

    def __init__(self) -> None:
        if not XAPI_API_KEY:
            raise RuntimeError("XAPI_KEY environment variable is not set")
        self.base_url = XAPI_BASE_URL
        self.headers = {
            "X-API-Key": XAPI_API_KEY,
            "Accept": "application/json",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _get(self, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = self.session.get(url, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            logger.error(
                "XAPI HTTP error | url=%s | status=%s | body=%s",
                url,
                exc.response.status_code if exc.response else "?",
                exc.response.text[:300] if exc.response else "",
            )
            raise
        except Exception as exc:
            logger.error("XAPI request failed | url=%s | error=%s", url, exc)
            raise

    def get_law_count(
        self,
        rettsomrade: Optional[str] = None,
        q: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> int:
        params: Dict[str, Any] = {"kilde": "alle", "limit": 1, "offset": 0}
        if rettsomrade:
            params["rettsomrade"] = rettsomrade
        if q:
            params["q"] = q
        if document_type:
            params["type"] = XAPI_TYPE_PARAM.get(document_type, document_type)
        data = self._get("/v1/lovdata/lover", params)
        return int(data.get("total", 0))

    def fetch_law_metadata_page(
        self,
        limit: int,
        offset: int,
        rettsomrade: Optional[str] = None,
        q: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"kilde": "alle", "limit": limit, "offset": offset}
        if rettsomrade:
            params["rettsomrade"] = rettsomrade
        if q:
            params["q"] = q
        if document_type:
            params["type"] = XAPI_TYPE_PARAM.get(document_type, document_type)
        data = self._get("/v1/lovdata/lover", params)
        return data.get("data", [])

    def fetch_law_detail(self, xapi_id: int) -> Dict[str, Any]:
        return self._get(f"/v1/lovdata/lover/{xapi_id}")

    def fetch_paragraphs(self, xapi_id: int) -> List[Dict[str, Any]]:
        data = self._get(
            f"/v1/lovdata/lover/{xapi_id}/paragrafer",
            params={"inkluder_opphevet": "false"},
        )
        if isinstance(data, list):
            return data
        return data.get("paragrafer", [])


# ---------------------------------------------------------------------------
# Paragraph field mapping
# ---------------------------------------------------------------------------


def map_paragraph(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map XAPI raw paragraph fields -> canonical storage format.

    XAPI field       -> storage field
    innhold_text     -> content_text   (used by main.py Step 3)
    innhold_html     -> content_html
    """
    return {
        "id": raw.get("id"),
        "paragraf_nr": raw.get("paragraf_nr"),
        "paragraf_id": raw.get("paragraf_id"),
        "paragraf_url": raw.get("paragraf_url"),
        "title": raw.get("tittel"),
        "content_html": raw.get("innhold_html"),
        "content_text": raw.get("innhold_text"),   # canonical key — do NOT change
        "repealed": bool(raw.get("opphevet", False)),
        "sort_order": raw.get("sortering"),
        "chapter_number": raw.get("kapittel_nr"),
        "chapter_title": raw.get("kapittel_tittel"),
    }

def build_law_json(
    *,
    domain_name: str,
    xapi_filter_type: str,
    xapi_filter_value: str,
    document_type: str,
    law_meta: Dict[str, Any],
    law_detail: Dict[str, Any],
    paragraphs_raw: List[Dict[str, Any]],
) -> Dict[str, Any]:
    dok_id: str = law_meta.get("dok_id", "")
    xapi_id: int = law_meta.get("id", 0)
    ref_id: str = law_meta.get("ref_id", "")

    source_doc_url = build_lovdata_source_url(dok_id=dok_id, ref_id=ref_id)
    xapi_law_url = build_xapi_doc_url(xapi_id)
    xapi_paragraphs_url = (
        f"{XAPI_BASE_URL}/v1/lovdata/lover/{xapi_id}/paragrafer?inkluder_opphevet=false"
    )
    storage_path = build_storage_path(dok_id)
    collected_at = datetime.now(timezone.utc).isoformat()

    paragraphs = [map_paragraph(p) for p in paragraphs_raw]

    return {
        "source": "xapi_lovdata",
        "document_type": document_type,
        "domain_matches": [
            {
                "domain_name": domain_name,
                "xapi_filter_type": xapi_filter_type,
                "xapi_filter_value": xapi_filter_value,
            }
        ],
        "metadata": {
            "id": xapi_id,
            "dok_id": dok_id,
            "ref_id": ref_id,
            "source_id": build_source_id(dok_id),
            "doc_title": law_meta.get("tittel"),
            "short_title": law_meta.get("korttittel"),
            "department": law_meta.get("departement"),
            "rettsomrade": law_meta.get("rettsomrade") or [],
            "effective_date": law_detail.get("dato_ikraft"),
            "last_changed_date": law_detail.get("dato_sist_endret"),
            "source_type": law_meta.get("kilde_type") or law_detail.get("kilde_type"),
            "paragraph_count": (
                law_detail.get("antall_paragrafer")
                or law_meta.get("antall_paragrafer")
                or len(paragraphs)
            ),
            "source_doc_url": source_doc_url,
            "xapi_doc_url": xapi_law_url,
        },
        "law_detail": law_detail,
        "paragraphs": paragraphs,
        "collection_info": {
            "collected_at": collected_at,
            "source_doc_url": source_doc_url,
            "xapi_law_url": xapi_law_url,
            "xapi_paragraphs_url": xapi_paragraphs_url,
            "storage_bucket": SUPABASE_XAPI_BUCKET,
            "storage_path": storage_path,
        },
    }
def build_metadata_payload(
    *,
    domain_name: str,
    document_type: str,
    law: Dict[str, Any],
    law_detail: Dict[str, Any],
    paragraph_count: int,
) -> Dict[str, Any]:
    dok_id: str = law.get("dok_id", "")
    xapi_id: int = law.get("id", 0)
    storage_path = build_storage_path(dok_id)
    source_doc_url = build_lovdata_source_url(
        dok_id=dok_id, ref_id=law.get("ref_id")
    )

    return {
        "dok_id": dok_id,
        "xapi_id": xapi_id,
        "source_id": build_source_id(dok_id),
        "document_type": document_type,
        "doc_title": law.get("tittel"),
        "short_title": law.get("korttittel"),
        "department": law.get("departement"),
        "domain_name": [domain_name],
        "subdomain": None,
        "rettsomrade": law.get("rettsomrade") or [],
        "paragraph_count": paragraph_count,
        "source_doc_url": source_doc_url,
        "xapi_doc_url": build_xapi_doc_url(xapi_id),
        "storage_bucket": SUPABASE_XAPI_BUCKET,
        "storage_path": storage_path,
        "file_format": "json",
        "content_type": "application/json",
        "fetch_status": "completed",
        "raw_metadata": law,
    }
class SupabaseXAPIStore:
    def __init__(self) -> None:
        self._client: Optional[Client] = None
        self._table: str = (
            os.environ.get("SUPABASE_XAPI_TABLE", "")
            or XAPI_METADATA_TABLE
        )
        self._bucket: str = (
            os.environ.get("SUPABASE_XAPI_BUCKET", "")
            or SUPABASE_XAPI_BUCKET
        )

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        return self._client

    # Expose table/bucket for external code that needs them
    @property
    def table_name(self) -> str:
        return self._table

    @property
    def bucket_name(self) -> str:
        return self._bucket

    def get_existing_row(self, dok_id: str) -> Optional[Dict[str, Any]]:
        try:
            resp = (
                self.client.table(self._table)
                .select("*")
                .eq("dok_id", dok_id)
                .limit(1)
                .execute()
            )
            if resp.data:
                return resp.data[0]
        except Exception as exc:
            logger.error("get_existing_row failed | dok_id=%s | error=%s", dok_id, exc)
        return None

    def append_domain_name(self, dok_id: str, domain_name: str) -> None:
        try:
            existing = self.get_existing_row(dok_id)
            if not existing:
                return
            current_domains: List[str] = existing.get("domain_name") or []
            if domain_name in current_domains:
                return
            updated = list(set(current_domains + [domain_name]))
            self.client.table(self._table).update(
                {
                    "domain_name": updated,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("dok_id", dok_id).execute()
            logger.info("Domain appended | dok_id=%s | domain=%s", dok_id, domain_name)
        except Exception as exc:
            logger.error("append_domain_name failed | dok_id=%s | error=%s", dok_id, exc)

    def upsert_metadata(self, payload: Dict[str, Any]) -> bool:
        """
        Upsert a metadata row by dok_id (ON CONFLICT dok_id -> update).
        Returns True on success.
        """
        try:
            now = datetime.now(timezone.utc).isoformat()
            payload = {**payload, "updated_at": now}
            if "created_at" not in payload:
                payload["created_at"] = now

            self.client.table(self._table).upsert(
                payload, on_conflict="dok_id"
            ).execute()
            return True
        except Exception as exc:
            logger.error(
                "upsert_metadata failed | dok_id=%s | error=%s",
                payload.get("dok_id"),
                exc,
            )
            return False

    def mark_failed(
        self,
        dok_id: str,
        error_message: str,
        document_type: str = "law",
    ) -> None:
        try:
            self.client.table(self._table).upsert(
                {
                    "dok_id": dok_id,
                    "document_type": document_type,
                    "storage_bucket": self._bucket,
                    "storage_path": build_storage_path(dok_id),
                    "fetch_status": "failed",
                    "error_message": str(error_message)[:1000],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="dok_id",
            ).execute()
        except Exception as exc:
            logger.error("mark_failed itself failed | dok_id=%s | error=%s", dok_id, exc)

    def upload_json_file(self, storage_path: str, content: bytes) -> bool:
        try:
            self.client.storage.from_(self._bucket).upload(
                path=storage_path,
                file=content,
                file_options={
                    "content-type": "application/json",
                    "upsert": "true",
                },
            )
            logger.info("Uploaded | bucket=%s | path=%s", self._bucket, storage_path)
            return True
        except Exception as exc:
            logger.error("upload_json_file failed | path=%s | error=%s", storage_path, exc)
            return False
    def process_law(client, store, law, domain_name, filter_type, filter_value):
        dok_id = law.get("dok_id")
        xapi_id = law.get("id")

        if not dok_id or not xapi_id:
            return

        try:
            existing = store.get_existing_row(dok_id)
            if existing:
                store.append_domain_name(dok_id, domain_name)
                return

            law_detail = client.fetch_law_detail(xapi_id)
            paragraphs = client.fetch_paragraphs(xapi_id)

            law_json = build_law_json(
                domain_name=domain_name,
                xapi_filter_type=filter_type,
                xapi_filter_value=filter_value,
                document_type="law",
                law_meta=law,
                law_detail=law_detail,
                paragraphs_raw=paragraphs,
            )

            metadata = build_metadata_payload(
                domain_name=domain_name,
                document_type="law",
                law=law,
                law_detail=law_detail,
                paragraph_count=len(paragraphs),
            )

            # upload JSON
            storage_path = build_storage_path(dok_id)
            store.upload_json_file(storage_path, json.dumps(law_json).encode("utf-8"))

            # upsert metadata
            store.upsert_metadata(metadata)

            logger.info("Processed | dok_id=%s", dok_id)

        except Exception as e:
            logger.error("Failed | dok_id=%s | error=%s", dok_id, e)
            store.mark_failed(dok_id, str(e))
    def run_domain_pipeline():
        client = XAPIClient()
        store = SupabaseXAPIStore()

        for domain_key in get_all_domain_keys():
            config = get_domain_config(domain_key)

            domain_name = config.get("domain_name", domain_key)
            rettsomrader = config.get("xapi_rettsomrader", [])
            q_values = config.get("q", [])

            logger.info("Processing domain: %s", domain_name)

            # -------- rettsomrade loop --------
            for rettsomrade in rettsomrader:
                total = client.get_law_count(rettsomrade=rettsomrade)

                for offset in range(0, total, XAPI_PAGE_SIZE):
                    laws = client.fetch_law_metadata_page(
                        limit=XAPI_PAGE_SIZE,
                        offset=offset,
                        rettsomrade=rettsomrade,
                    )

                    for law in laws:
                        process_law(client, store, law, domain_name, "rettsomrade", rettsomrade)

            # -------- q loop --------
            for q in q_values:
                total = client.get_law_count(q=q)

                for offset in range(0, total, XAPI_PAGE_SIZE):
                    laws = client.fetch_law_metadata_page(
                        limit=XAPI_PAGE_SIZE,
                        offset=offset,
                        q=q,
                    )

                    for law in laws:
                        process_law(client, store, law, domain_name, "q", q)