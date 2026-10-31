"""Plain-file cache for bulk downloads. Writes only inside the cache directory."""
import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,80}\.json$")
TTL_DAYS = 90  # quarterly refresh


def cache_dir() -> Path:
    base = os.environ.get("HIGHERED_MCPS_CACHE") or str(Path.home() / ".cache" / "highered-mcps")
    return Path(base).expanduser().resolve() / "risk"


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


def read(name: str) -> dict | None:
    """Return {'data', 'meta'} or None if absent/corrupt (checksum mismatch counts as corrupt)."""
    path = safe_path(name)
    try:
        blob = json.loads(path.read_text())
        if blob["meta"]["sha256"] != _digest(blob["data"]):
            return None
        return blob
    except (OSError, ValueError, KeyError, TypeError):
        return None


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
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"meta": meta, "data": data}, separators=(",", ":")))
    os.replace(tmp, path)
    return meta


def is_fresh(meta: dict, ttl_days: int = TTL_DAYS) -> bool:
    try:
        got = datetime.fromisoformat(meta["retrieved_at"])
    except (KeyError, ValueError):
        return False
    return datetime.now(UTC) - got < timedelta(days=ttl_days)
