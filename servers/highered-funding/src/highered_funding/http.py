"""Guarded outbound HTTP: HTTPS only, host allowlist, manual redirects, size cap, bounded retries.

Error messages never include URLs, query strings, headers, or local paths.
"""
import asyncio
import json
import logging
import time
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("highered_funding")

ALLOWED_HOSTS = frozenset(
    {
        "ncses.nsf.gov",
        "api.nsf.gov",
        "api.reporter.nih.gov",
        "api.grants.gov",
        "shef.sheeo.org",
        "www.wiche.edu",
    }
)
# POST is used only for the two search APIs that require it. Both are read-only queries.
POST_HOSTS = frozenset({"api.reporter.nih.gov", "api.grants.gov"})
MAX_REDIRECTS = 3
MAX_ATTEMPTS = 3
RETRY_STATUS = {429, 500, 502, 503, 504}
# NIH asks for at most one request per second; the others are paced the same way to be polite.
MIN_INTERVAL = {"api.reporter.nih.gov": 1.0, "api.grants.gov": 1.0, "api.nsf.gov": 1.0, "ncses.nsf.gov": 1.0, "shef.sheeo.org": 1.0, "www.wiche.edu": 1.0}


class _Result:
    def __init__(self, status_code: int, location: str, content: bytes):
        self.status_code, self.location, self.content = status_code, location, content

    @property
    def is_redirect(self) -> bool:
        return self.status_code in (301, 302, 303, 307, 308) and bool(self.location)


class UpstreamError(Exception):
    """Safe-to-show failure from an upstream call."""


class NotFound(UpstreamError):
    pass


def check_url(url: str, allowed: frozenset[str] = ALLOWED_HOSTS) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UpstreamError("Blocked request: only https is allowed.")
    if parts.username or parts.password or parts.port not in (None, 443):
        raise UpstreamError("Blocked request: unexpected URL form.")
    if (parts.hostname or "").lower() not in allowed:
        raise UpstreamError("Blocked request: host is not on the allowlist.")
    return parts.hostname.lower()


class Guard:
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        allowed: frozenset[str] = ALLOWED_HOSTS,
        backoff: float = 1.0,
        min_interval: dict[str, float] | None = None,
    ):
        self._client = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            verify=True,
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": "highered-mcps/0.1 (read-only MCP)"},
        )
        self._allowed = allowed
        self._backoff = backoff
        self._min_interval = MIN_INTERVAL if min_interval is None else min_interval
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}  # one per host, so waiting on one host never delays another

    async def _pace(self, host: str) -> None:
        gap = self._min_interval.get(host, 0.0)
        if not gap:
            return
        async with self._locks.setdefault(host, asyncio.Lock()):
            wait = self._last.get(host, 0.0) + gap - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[host] = time.monotonic()

    async def get_json(self, url, params=None, headers=None, max_bytes=5_000_000, attempts=MAX_ATTEMPTS):
        """GET and parse JSON. Returns (data, public_url). Secrets belong in `headers` only."""
        body, public_url = await self.get_bytes(url, params, headers, max_bytes, attempts)
        try:
            return json.loads(body), public_url
        except ValueError:
            raise UpstreamError(f"{urlsplit(public_url).hostname} returned a non-JSON response.") from None

    async def post_json(self, url: str, body: dict, max_bytes: int = 5_000_000, attempts: int = MAX_ATTEMPTS):
        """POST a JSON search query (read-only APIs only). Redirects are not followed. Returns (data, public_url)."""
        host = check_url(url, self._allowed)
        if host not in POST_HOSTS:
            raise UpstreamError("Blocked request: POST is not allowed for this host.")
        for attempt in range(min(attempts, MAX_ATTEMPTS)):
            if attempt:
                await asyncio.sleep(self._backoff * 2 ** (attempt - 1))
            await self._pace(host)
            try:
                async with self._client.stream("POST", url, json=body) as r:
                    declared = r.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise UpstreamError("Upstream response exceeds the size limit.")
                    buf = bytearray()
                    async for chunk in r.aiter_bytes():
                        buf.extend(chunk)
                        if len(buf) > max_bytes:
                            raise UpstreamError("Upstream response exceeds the size limit.")
                    status = r.status_code
            except httpx.TransportError:
                continue
            if status in RETRY_STATUS and attempt < min(attempts, MAX_ATTEMPTS) - 1:
                continue
            if 300 <= status < 400:
                raise UpstreamError(f"{host} redirected a POST; not followed.")
            if status >= 400:
                raise UpstreamError(f"{host} returned HTTP {status}.")
            try:
                return json.loads(bytes(buf)), url
            except ValueError:
                raise UpstreamError(f"{host} returned a non-JSON response.") from None
        log.warning("upstream unreachable: %s", host)
        raise UpstreamError(f"Could not reach {host}.") from None

    async def get_bytes(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        max_bytes: int = 5_000_000,
        attempts: int = MAX_ATTEMPTS,
    ) -> tuple[bytes, str]:
        """GET raw bytes with the size cap. Returns (body, public_url)."""
        public_url = str(httpx.URL(url).copy_merge_params(params or {}))
        current = public_url
        for _hop in range(MAX_REDIRECTS + 1):
            host = check_url(current, self._allowed)
            resp = await self._fetch(current, headers, host, max_bytes, min(attempts, MAX_ATTEMPTS))
            if resp.is_redirect:
                current = str(httpx.URL(current).join(resp.location))
                continue
            if resp.status_code == 404:
                raise NotFound("Upstream returned 404 (not found).")
            if resp.status_code >= 400:
                raise UpstreamError(f"{host} returned HTTP {resp.status_code}.")
            return resp.content, public_url
        raise UpstreamError("Too many redirects.")

    async def _fetch(self, url, headers, host, max_bytes, attempts) -> "_Result":
        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(self._backoff * 2 ** (attempt - 1))
            await self._pace(host)
            try:
                async with self._client.stream("GET", url, headers=headers) as r:
                    declared = r.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise UpstreamError("Upstream response exceeds the size limit.")
                    buf = bytearray()
                    async for chunk in r.aiter_bytes():
                        buf.extend(chunk)
                        if len(buf) > max_bytes:
                            raise UpstreamError("Upstream response exceeds the size limit.")
                    if r.status_code in RETRY_STATUS and attempt < attempts - 1:
                        continue
                    return _Result(r.status_code, r.headers.get("location", ""), bytes(buf))
            except httpx.TransportError:
                continue
        log.warning("upstream unreachable: %s", host)
        raise UpstreamError(f"Could not reach {host}.") from None

    async def aclose(self) -> None:
        await self._client.aclose()
