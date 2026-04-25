"""
services/lovdata_title_fetcher.py

Resolves a human-readable title for any Lovdata URL.

Three-layer strategy (fastest to slowest):
  Layer 1 - Redis cache  : instant, zero network
  Layer 2 - Supabase DB  : fast, survives Redis eviction / server restart
  Layer 3 - httpx fetch  : parse <title> from Lovdata HTML, then back-fill L1 + L2

Redis key : lovdata_title:{base_url}   (section anchors stripped before lookup)
Supabase  : table "lovdata_url_titles" (url TEXT PK, title TEXT, fetched_at TIMESTAMPTZ)
Redis TTL : 7 days (604 800 s) — Lovdata titles almost never change
"""

import logging
import re
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Strip section anchors (e.g. /§7, /§13-3) before cache lookup so all
# sections of the same law share one cached title.
_ANCHOR_RE = re.compile(r"/§.*$")

# Lovdata <title> tags look like:
#   "Lov om foretaksregisteret (foretaksregisterloven) - Lovdata"
# Strip the trailing site suffix.
_SITE_SUFFIX_RE = re.compile(r"\s*[-–|]\s*Lovdata\s*$", re.IGNORECASE)

_REDIS_TTL   = 604_800   # 7 days in seconds
_HTTP_TIMEOUT = 6.0      # seconds per fetch


def _base_url(url: str) -> str:
    """Strip section anchor so /§7 and /§13 resolve to the same cache key."""
    return _ANCHOR_RE.sub("", url.rstrip("/"))


def _parse_title_from_html(html: str) -> Optional[str]:
    """
    Extract the best title from Lovdata HTML.

    Priority:
      1. <h1> with a 'title' class  — full Norwegian document title
      2. <title> tag                — always present, slightly shorter
    """
    # Try <h1 class="...title..."> first
    h1 = re.search(
        r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h1>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if h1:
        raw = re.sub(r"<[^>]+>", "", h1.group(1)).strip()
        if raw:
            return raw

    # Fallback: <title> tag
    t = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if t:
        raw = re.sub(r"<[^>]+>", "", t.group(1)).strip()
        raw = _SITE_SUFFIX_RE.sub("", raw).strip()
        if raw:
            return raw

    return None


class LovdataTitleFetcher:
    """
    Resolve human-readable Norwegian titles for Lovdata URLs.

    Inject into MessageService (and optionally chat.py) so titles are
    available both at save time (stored in Supabase) and at stream time
    (sent over the WebSocket in the 'complete' event).

    Usage:
        fetcher = LovdataTitleFetcher(redis_client, supabase_client)
        titles  = await fetcher.resolve_titles(["https://lovdata.no/lov/..."])
        # {"https://lovdata.no/lov/...": "Lov om ..."}
    """

    def __init__(self, redis_client, supabase_client) -> None:
        self._redis    = redis_client
        self._supabase = supabase_client
        logger.info("LovdataTitleFetcher initialized")

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def resolve_titles(self, urls: List[str]) -> Dict[str, str]:
        """
        Resolve titles for a list of Lovdata URLs.

        Returns {original_url: title}.
        URLs that cannot be resolved map to their own URL string
        (last-resort — the UI always shows something).
        """
        result: Dict[str, str] = {}
        need_fetch: List[str]  = []

        # Layer 1 (Redis) then Layer 2 (Supabase)
        for url in urls:
            base  = _base_url(url)
            title = self._redis_get(base)
            if title:
                result[url] = title
                logger.debug(f"L1 Redis hit | {base}")
                continue

            title = self._supabase_get(base)
            if title:
                result[url] = title
                self._redis_set(base, title)   # back-fill Redis
                logger.debug(f"L2 Supabase hit | {base}")
                continue

            need_fetch.append(url)

        # Layer 3: HTTP fetch — deduplicated by base URL
        fetched_bases: Dict[str, str] = {}   # base_url -> resolved title
        for url in need_fetch:
            base = _base_url(url)
            if base in fetched_bases:
                result[url] = fetched_bases[base]
                continue

            title = await self._http_fetch(base)
            if title:
                self._redis_set(base, title)
                self._supabase_set(base, title)
                fetched_bases[base] = title
                result[url] = title
                logger.info(f"L3 fetched | {base} -> '{title[:70]}'")
            else:
                fetched_bases[base] = url   # raw URL as last resort
                result[url] = url
                logger.warning(f"Title fetch failed | {base} — using raw URL")

        return result

    # ------------------------------------------------------------------ #
    # Layer 1 — Redis                                                      #
    # ------------------------------------------------------------------ #

    def _redis_key(self, base_url: str) -> str:
        return f"lovdata_title:{base_url}"

    def _redis_get(self, base_url: str) -> Optional[str]:
        try:
            raw = self._redis._client.get(self._redis_key(base_url))
            if raw:
                return raw.decode() if isinstance(raw, bytes) else str(raw)
        except Exception as exc:
            logger.debug(f"Redis get error | {exc}")
        return None

    def _redis_set(self, base_url: str, title: str) -> None:
        try:
            self._redis._client.setex(self._redis_key(base_url), _REDIS_TTL, title)
        except Exception as exc:
            logger.debug(f"Redis set error | {exc}")

    # ------------------------------------------------------------------ #
    # Layer 2 — Supabase  (table: lovdata_url_titles)                     #
    # ------------------------------------------------------------------ #

    def _supabase_get(self, base_url: str) -> Optional[str]:
        try:
            resp = (
                self._supabase.table("lovdata_url_titles")
                .select("title")
                .eq("url", base_url)
                .limit(1)
                .execute()
            )
            rows = resp.data or []
            if rows:
                return rows[0]["title"]
        except Exception as exc:
            logger.debug(f"Supabase title get error | {exc}")
        return None

    def _supabase_set(self, base_url: str, title: str) -> None:
        try:
            self._supabase.table("lovdata_url_titles").upsert(
                {"url": base_url, "title": title},
                on_conflict="url",
            ).execute()
        except Exception as exc:
            logger.debug(f"Supabase title upsert error | {exc}")

    # ------------------------------------------------------------------ #
    # Layer 3 — httpx fetch                                               #
    # ------------------------------------------------------------------ #

    async def _http_fetch(self, base_url: str) -> Optional[str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            async with httpx.AsyncClient(
                timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
            ) as client:
                resp = await client.get(base_url, headers=headers)
                resp.raise_for_status()
                return _parse_title_from_html(resp.text)
        except httpx.TimeoutException:
            logger.warning(f"Lovdata fetch timeout | {base_url}")
        except httpx.HTTPStatusError as exc:
            logger.warning(f"Lovdata HTTP {exc.response.status_code} | {base_url}")
        except Exception as exc:
            logger.warning(f"Lovdata fetch error | {base_url} | {exc}")
        return None