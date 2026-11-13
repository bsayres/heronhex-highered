"""Plain-file cache for bulk downloads. Writes only inside the cache directory.

Reads are memoized in-process, keyed by the file's size and mtime: a shared server answers hundreds of calls from the same few
files, and re-parsing and re-hashing a multi-megabyte JSON file on every call would block the event loop. A file replaced on disk
(by `write` here or by another process) is re-read on the next call.
"""
import hashlib
import json
import os
import re
import secrets
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,80}\.json\Z")
TTL_DAYS = 90  # quarterly refresh
MEMO_ENTRIES = 64

_memo: OrderedDict[str, tuple[tuple[int, int], dict | None]] = OrderedDict()


def cache_dir() -> Path:
    base = os.environ.get("HIGHERED_MCPS_CACHE") or str(Path.home() / ".cache" / "highered-mcps")
    return Path(base).expanduser().resolve() / "institutions"


def safe_path(name: str) -> Path:
    if not NAME_RE.match(name) or ".." in name:
        raise ValueError("Invalid cache file name.")
    root = cache_dir()
    path = (root / name).resolve()
    if path.parent != root:
        raise ValueError("Cache path escapes the cache directory.")
    return path


def _digest(data: object) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


def read(name: str) -> dict | None:
    """Return {'data', 'meta'} or None if absent/corrupt (checksum mismatch counts as corrupt). Callers must not mutate the result."""
    path = safe_path(name)
    key = str(path)
    stamp = _stamp(path)
    if stamp is None:
        _memo.pop(key, None)
        return None
    hit = _memo.get(key)
    if hit is not None and hit[0] == stamp:
        _memo.move_to_end(key)
        return hit[1]
    try:
        blob = json.loads(path.read_text())
        if blob["meta"]["sha256"] != _digest(blob["data"]):
            blob = None
    except (OSError, ValueError, KeyError, TypeError):
        blob = None
    _memo[key] = (stamp, blob)
    _memo.move_to_end(key)
    while len(_memo) > MEMO_ENTRIES:
        _memo.popitem(last=False)
    return blob


def write(name: str, data: object, as_of: str, source_url: str, **extra) -> dict:
    path = safe_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "sha256": _digest(data),
        "as_of": as_of,
        **extra,
        "source_url": source_url,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    # A per-write temp name, so two processes refreshing the same file never interleave inside one temp file.
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{secrets.token_hex(4)}.tmp")
    tmp.write_text(json.dumps({"meta": meta, "data": data}, separators=(",", ":")))
    os.replace(tmp, path)
    _memo.pop(str(path), None)
    return meta


def is_fresh(meta: dict, ttl_days: int = TTL_DAYS) -> bool:
    try:
        got = datetime.fromisoformat(meta["retrieved_at"])
    except (KeyError, ValueError):
        return False
    return datetime.now(UTC) - got < timedelta(days=ttl_days)
