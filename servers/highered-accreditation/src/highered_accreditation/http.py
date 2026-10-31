"""Guarded outbound HTTP: HTTPS only, host allowlist, no redirects on POST, size cap, bounded retries.

The only request this server makes is the DAPIP data-file download, a fixed POST that the
site's own Download button sends. Error messages never include URLs, headers, or local paths.
"""
import asyncio
import logging
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("highered_accreditation")

ALLOWED_HOSTS = frozenset({"ope.ed.gov"})
DAPIP_PAGE = "https://ope.ed.gov/dapip/"
DOWNLOAD_URL = "https://ope.ed.gov/dapip/api/downloadFiles/accreditationDataFiles"
# The body is fixed and never built from user input.
DOWNLOAD_BODY = {"CSVChecked": True, "ExcelChecked": False}
# POST is allowed to exactly this URL and nothing else.
POST_URLS = frozenset({DOWNLOAD_URL})
MAX_ATTEMPTS = 3
RETRY_STATUS = {429, 500, 502, 503, 504}


class UpstreamError(Exception):
    """Safe-to-show failure from an upstream call."""


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
    ):
        self._client = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            verify=True,
            timeout=httpx.Timeout(60.0),
            headers={"User-Agent": "highered-mcps/0.1 (read-only MCP)"},
        )
        self._allowed = allowed
        self._backoff = backoff

    async def post_download(self, url: str = DOWNLOAD_URL, max_bytes: int = 15_000_000, attempts: int = MAX_ATTEMPTS) -> bytes:
        """POST the fixed DAPIP download request and return the body (size-capped). Redirects are not followed."""
        host = check_url(url, self._allowed)
        if url not in POST_URLS:
            raise UpstreamError("Blocked request: POST is not allowed for this URL.")
        for attempt in range(min(attempts, MAX_ATTEMPTS)):
            if attempt:
                await asyncio.sleep(self._backoff * 2 ** (attempt - 1))
            try:
                async with self._client.stream("POST", url, json=DOWNLOAD_BODY) as r:
                    declared = r.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise UpstreamError("Upstream response exceeds the size limit.")
                    buf = bytearray()
                    async for chunk in r.aiter_bytes():
                        buf.extend(chunk)
                        if len(buf) > max_bytes:
                            raise UpstreamError("Upstream response exceeds the size limit.")
                    if r.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
                        continue
                    if 300 <= r.status_code < 400:
                        raise UpstreamError(f"{host} redirected the download request; not followed.")
                    if r.status_code >= 400:
                        raise UpstreamError(f"{host} returned HTTP {r.status_code}.")
                    return bytes(buf)
            except httpx.TransportError:
                continue
        log.warning("upstream unreachable: %s", host)
        raise UpstreamError(f"Could not reach {host}.") from None

    async def aclose(self) -> None:
        await self._client.aclose()
