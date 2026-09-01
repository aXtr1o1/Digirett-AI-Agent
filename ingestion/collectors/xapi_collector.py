from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from ingestion.src.config import Settings, settings

logger = logging.getLogger(__name__)


class XAPIResponseShapeError(Exception):
    """Raised when an API response does not match the expected schema shape."""
    pass


@dataclass(frozen=True)
class Page:
    items: List[Dict[str, Any]]
    total: Optional[int]
    raw: Any


class XAPICollector:
    """Async XAPI Collector for live xAPI endpoints with rate limiting & exponential backoff."""

    def __init__(self, config_settings: Optional[Settings] = None):
        self.settings = config_settings or settings
        self._semaphore = asyncio.Semaphore(self.settings.xapi_concurrency)
        self._client = httpx.AsyncClient(
            base_url=self.settings.xapi_base_url,
            timeout=self.settings.xapi_timeout_seconds,
            headers=self._build_headers(),
            follow_redirects=True,
        )

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.settings.xapi_bearer_token:
            headers["Authorization"] = f"Bearer {self.settings.xapi_bearer_token}"
        if self.settings.xapi_api_key:
            headers[self.settings.xapi_api_key_header] = self.settings.xapi_api_key
        return headers

    async def __aenter__(self) -> "XAPICollector":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._client.aclose()

    async def close(self) -> None:
        await self._client.aclose()

    async def _wait_for_network_recovery(self, check_interval: float = 10.0) -> None:
        """Pauses execution and probes network connectivity until Wi-Fi / Internet is restored."""
        logger.warning("⚠️ [NETWORK OFFLINE] Connection lost or unreachable. Pausing ingestion. Waiting for Wi-Fi / Internet reconnection...")
        import socket
        while True:
            await asyncio.sleep(check_interval)
            is_online = False
            for host, port in [("8.8.8.8", 53), ("1.1.1.1", 53)]:
                try:
                    with socket.create_connection((host, port), timeout=4.0):
                        is_online = True
                        break
                except OSError:
                    pass

            if is_online:
                logger.info("✅ [NETWORK RESTORED] Internet / xAPI connection re-established. Resuming ingestion...")
                try:
                    await self._client.aclose()
                except Exception:
                    pass
                self._client = httpx.AsyncClient(
                    base_url=self.settings.xapi_base_url,
                    timeout=self.settings.xapi_timeout_seconds,
                    headers=self._build_headers(),
                    follow_redirects=True,
                )
                return
            logger.warning("⏳ [WAITING FOR WI-FI] Still disconnected. Retrying in %ds...", int(check_interval))

    async def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        clean_params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        last_error: Optional[Exception] = None

        attempt = 0
        while attempt <= self.settings.xapi_max_retries:
            try:
                async with self._semaphore:
                    if self.settings.xapi_request_pacing_seconds > 0:
                        await asyncio.sleep(self.settings.xapi_request_pacing_seconds)
                    response = await self._client.get(path, params=clean_params)

                response.raise_for_status()
                try:
                    return response.json()
                except json.JSONDecodeError as exc:
                    raise XAPIResponseShapeError(
                        f"GET {path} returned non-JSON content (content-type={response.headers.get('content-type')})"
                    ) from exc

            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, httpx.RemoteProtocolError) as net_exc:
                logger.warning("⚠️ Network connection dropped during GET %s (%s)", path, net_exc)
                await self._wait_for_network_recovery()
                # Do not increment attempt count for general network loss; retry immediately upon recovery
                continue

            except (httpx.HTTPError, XAPIResponseShapeError) as exc:
                last_error = exc
                retryable = isinstance(exc, XAPIResponseShapeError)
                if isinstance(exc, httpx.HTTPStatusError):
                    retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
                elif isinstance(exc, httpx.RequestError):
                    retryable = True

                if not retryable or attempt >= self.settings.xapi_max_retries:
                    break
                delay = self.settings.xapi_backoff_seconds * (2**attempt)
                logger.warning("GET %s failed (%s); retrying in %.1fs (attempt %d/%d)", path, exc, delay, attempt + 1, self.settings.xapi_max_retries)
                await asyncio.sleep(delay)
                attempt += 1

        assert last_error is not None
        raise last_error

    # ----------------------------- Parsers -----------------------------

    @staticmethod
    def parse_areas(payload: Any) -> Page:
        if not isinstance(payload, dict):
            raise XAPIResponseShapeError(f"rettsomrader: expected JSON object, got {type(payload).__name__}")

        rettsomrader = payload.get("rettsomrader")
        if isinstance(rettsomrader, list):
            items = []
            for value in rettsomrader:
                if isinstance(value, str) and value.strip():
                    items.append({"rettsomrade": value.strip()})
                elif isinstance(value, dict) and value.get("rettsomrade"):
                    items.append(value)
            return Page(items=items, total=_int_or_none(payload.get("total")), raw=payload)

        data = payload.get("data")
        if isinstance(data, list):
            items = [item for item in data if isinstance(item, dict) and item.get("rettsomrade")]
            return Page(items=items, total=_int_or_none(payload.get("total")), raw=payload)

        raise XAPIResponseShapeError(f"rettsomrader: unsupported response shape. Keys={list(payload.keys())}")

    @staticmethod
    def parse_laws(payload: Any) -> Page:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise XAPIResponseShapeError("laws: expected {'total','limit','offset','data'} shape")
        items = [x for x in payload["data"] if isinstance(x, dict)]
        return Page(items=items, total=_int_or_none(payload.get("total")), raw=payload)

    @staticmethod
    def parse_paragraphs(payload: Any) -> Page:
        if isinstance(payload, list):
            items = [x for x in payload if isinstance(x, dict)]
            return Page(items=items, total=len(items), raw=payload)
        if not isinstance(payload, dict):
            raise XAPIResponseShapeError(f"paragraphs: expected dict or list, got {type(payload).__name__}")
        paragrafer = payload.get("paragrafer")
        if paragrafer is None:
            paragrafer = payload.get("data")
        if paragrafer is None:
            return Page(items=[], total=0, raw=payload)
        if isinstance(paragrafer, list):
            items = [x for x in paragrafer if isinstance(x, dict)]
            return Page(items=items, total=len(items), raw=payload)
        return Page(items=[], total=0, raw=payload)

    @staticmethod
    def parse_central_regulations(payload: Any) -> Page:
        if not isinstance(payload, dict):
            raise XAPIResponseShapeError("central regulations: response must be an object")
        sentrale = payload.get("sentrale")
        if isinstance(sentrale, dict) and isinstance(sentrale.get("forskrifter"), list):
            items = [x for x in sentrale["forskrifter"] if isinstance(x, dict)]
            return Page(items=items, total=_int_or_none(sentrale.get("antall_totalt")), raw=payload)
        if isinstance(payload.get("forskrifter"), list):
            items = [x for x in payload["forskrifter"] if isinstance(x, dict)]
            return Page(items=items, total=_int_or_none(payload.get("antall_totalt")) or len(items), raw=payload)
        if isinstance(payload.get("data"), list):
            items = [x for x in payload["data"] if isinstance(x, dict)]
            return Page(items=items, total=_int_or_none(payload.get("total")) or len(items), raw=payload)
        raise XAPIResponseShapeError(f"central regulations: expected 'sentrale' with 'forskrifter' list, got keys={list(payload.keys())}")

    @staticmethod
    def parse_law_linked_regulations(payload: Any) -> Page:
        if not isinstance(payload, dict) or not isinstance(payload.get("forskrifter"), list):
            raise XAPIResponseShapeError("law-linked regulations: expected {'lov', 'antall_totalt', 'forskrifter': [...]}")
        items = [x for x in payload["forskrifter"] if isinstance(x, dict)]
        total = _int_or_none(payload.get("antall_totalt")) or _int_or_none(payload.get("antall_forskrifter"))
        return Page(items=items, total=total, raw=payload)

    # ------------------------------- Pagination ---------------------------------

    async def _paginate_offset(
        self,
        path: str,
        params: Dict[str, Any],
        parser: Callable[[Any], Page],
    ) -> Tuple[List[Dict[str, Any]], List[Any], Optional[int]]:

        all_items: List[Dict[str, Any]] = []
        raw_pages: List[Any] = []
        offset = 0
        reported_total: Optional[int] = None

        for page_number in range(self.settings.xapi_max_pages):
            page_params = dict(params)
            page_params["limit"] = self.settings.xapi_limit
            page_params["offset"] = offset

            payload = await self._get_json(path, page_params)
            page = parser(payload)
            raw_pages.append(payload)

            received = len(page.items)
            if reported_total is None and page.total is not None:
                reported_total = page.total

            all_items.extend(page.items)

            logger.info("Pagination %s: page=%d offset=%d received=%d collected=%d total=%s",
                        path, page_number + 1, offset, received, len(all_items), reported_total)

            if reported_total is not None and len(all_items) >= reported_total:
                break
            if received == 0:
                break
            offset += received
            if reported_total is None and received < self.settings.xapi_limit:
                break
        else:
            raise RuntimeError(f"Pagination exceeded XAPI_MAX_PAGES={self.settings.xapi_max_pages} for {path}")

        return all_items, raw_pages, reported_total

    # -------------------------------- Endpoints ---------------------------------

    async def get_areas(self) -> Tuple[List[Dict[str, Any]], List[Any], Optional[int]]:
        payload = await self._get_json(self.settings.xapi_areas_path)
        page = self.parse_areas(payload)
        return page.items, [payload], page.total

    async def get_laws_by_area(
        self, rettsomrade: str
    ) -> Tuple[List[Dict[str, Any]], List[Any], Optional[int]]:
        params: Dict[str, Any] = {
            self.settings.xapi_law_area_param: rettsomrade,
            "type": self.settings.xapi_law_type,
        }
        return await self._paginate_offset(self.settings.xapi_laws_path, params, self.parse_laws)

    async def get_law_detail(self, law_lookup_id: int | str) -> Dict[str, Any]:
        path = self.settings.xapi_law_detail_path.format(id=quote(str(law_lookup_id), safe=""))
        payload = await self._get_json(path)
        if not isinstance(payload, dict):
            raise XAPIResponseShapeError("law detail: expected a JSON object")
        return payload

    async def get_law_paragraphs(
        self, law_lookup_id: int | str
    ) -> Tuple[List[Dict[str, Any]], List[Any], Optional[int]]:
        path = self.settings.xapi_law_paragraphs_path.format(id=quote(str(law_lookup_id), safe=""))
        params: Dict[str, Any] = {}
        if self.settings.xapi_include_removed_paragraphs:
            params["include_removed"] = True
        payload = await self._get_json(path, params)
        page = self.parse_paragraphs(payload)
        return page.items, [payload], page.total

    async def get_law_detail(self, law_id: int | str) -> Dict[str, Any]:
        """Fetches complete law metadata from /v1/lovdata/lover/{id}."""
        path = self.settings.xapi_law_detail_path.format(id=law_id)
        try:
            payload = await self._get_json(path)
            if isinstance(payload, dict):
                return payload.get("data") if "data" in payload else payload
        except Exception as exc:
            logger.warning("get_law_detail failed for law_id=%s: %s", law_id, exc)
        return {}

    async def get_central_regulations_for_domain(
        self, rettsomrader: List[str]
    ) -> Tuple[List[Dict[str, Any]], List[Any], Optional[int]]:
        all_items: List[Dict[str, Any]] = []
        all_raw: List[Any] = []
        total_count = 0

        for area in rettsomrader:
            if not area:
                continue
            params: Dict[str, Any] = {
                "type": self.settings.xapi_central_regulation_type,
                self.settings.xapi_regulation_area_param: area,
                "include_fulltext": self.settings.xapi_include_regulation_fulltext,
            }
            try:
                items, raw_pages, area_total = await self._paginate_offset(
                    self.settings.xapi_regulations_path, params, self.parse_central_regulations
                )
                for item in items:
                    item["rettsomrade_filter"] = area
                all_items.extend(items)
                all_raw.extend(raw_pages)
                total_count += (area_total or len(items))
            except Exception as exc:
                logger.warning("Error fetching central regulations for area '%s': %s", area, exc)

        return all_items, all_raw, total_count

    async def get_regulations_for_law(
        self, law_dok_id: str, domain_rettsomrader: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], List[Any], Optional[int]]:
        encoded = quote(law_dok_id, safe="")
        path = self.settings.xapi_law_regulations_path.format(law_doc_id=encoded)
        params: Dict[str, Any] = {
            "include_fulltext": self.settings.xapi_include_regulation_fulltext,
        }
        if self.settings.filter_linked_regulations_by_domain and domain_rettsomrader:
            params[self.settings.xapi_regulation_area_param] = ",".join(domain_rettsomrader)
        return await self._paginate_offset(path, params, self.parse_law_linked_regulations)



def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None