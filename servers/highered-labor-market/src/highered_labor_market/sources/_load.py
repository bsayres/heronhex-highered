"""Shared on-demand cache loader: fresh cache, else download + parse + cache, else stale copy on failure."""
import hashlib
from collections.abc import Awaitable, Callable

from .. import cache
from ..http import UpstreamError


class Loaded:
    def __init__(self, data, meta: dict, stale: bool):
        self.data, self.meta, self.stale = data, meta, stale


async def load(name: str, ttl_days: int, fetch: Callable[[], Awaitable[tuple[object, str, str, dict]]]) -> Loaded:
    """`fetch` returns (parsed, as_of, source_url, extra_meta) where extra_meta may hold file_sha256."""
    hit = cache.read(name)
    if hit and cache.is_fresh(hit["meta"], ttl_days):
        return Loaded(hit["data"], hit["meta"], False)
    try:
        parsed, as_of, url, extra = await fetch()
    except UpstreamError:
        if hit:
            return Loaded(hit["data"], hit["meta"], True)
        raise
    return Loaded(parsed, cache.write(name, parsed, as_of, url, **extra), False)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
