"""Projections Central (State Projections Consortium, funded by the U.S. DOL Employment and Training Administration):
state and national occupational employment projections through its public, read-only REST API. No key.

One request can return several areas (state FIPS joined with '+', 0 = United States) and several occupations (SOC codes joined
with '+'). Each state agency produces its own projections, so projection years can differ from BLS national projections and
between states; every row carries its own base and projection years. Rows are checked against what was asked for: the API
returns an empty result for an unknown filter, but nothing here relies on that.
"""
import re
from datetime import UTC, datetime, timedelta

from .. import cache
from ..http import Guard, NotFound, UpstreamError

BASE = "https://public.projectionscentral.org/Projections"
SOURCE = "Projections Central (State Projections Consortium; funded by U.S. DOL ETA)"
ENDPOINT = {"long": "LongTermRestJson", "short": "ShortTermRestJson"}
SOC_RE = re.compile(r"^[0-9]{2}-[0-9]{4}\Z")
YEAR_RE = re.compile(r"^[0-9]{4}\Z")
TTL_DAYS = 90
BATCH = 100
US = "0"
DISCLAIMER = ("Projections Central: 'Projection data accessible from this site are the responsibility of each agency that developed the projections. "
              "The accuracy of projections for individual occupations is subject to error because of the many unknown factors that will affect the economy "
              "over the projection period.' Projections should not be the sole basis for a choice of career.")


def _int(v) -> int | None:
    try:
        return int(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _float(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def row(r: dict) -> dict | None:
    """Validate and normalize one API row; None if it is not shaped like a projection row."""
    if not isinstance(r, dict) or not SOC_RE.match(str(r.get("OccCode", ""))) or not str(r.get("STFIPS", "")).isdigit():
        return None
    by, py = str(r.get("BaseYear", "")), str(r.get("ProjYear", ""))
    if not (YEAR_RE.match(by) and YEAR_RE.match(py)):
        return None
    url = str(r.get("StateURL") or "")
    return {
        "fips": str(int(r["STFIPS"])), "area": str(r.get("Area", "")).strip(), "soc": r["OccCode"], "title": str(r.get("Title", "")).strip(),
        "base": _int(r.get("Base")), "projected": _int(r.get("Projected")), "change": _int(r.get("Change")), "percent_change": _float(r.get("PercentChange")),
        "annual_openings": _int(r.get("AvgAnnualOpenings")), "base_year": int(by), "projection_year": int(py),
        "agency_url": url if url.startswith("https://") and len(url) <= 300 and not re.search(r"\s", url) else None,
    }


def broad(soc: str) -> str:
    return soc[:-1] + "0"


def request_codes(socs: list[str]) -> list[str]:
    """The occupations asked for plus their broad-group codes, which some areas report instead of the detailed code."""
    out: list[str] = []
    for s in socs:
        for c in (s, broad(s)):
            if c not in out:
                out.append(c)
    return out


def pick(entries: dict, fips: str, soc: str) -> tuple[dict | None, str]:
    """(row, 'exact' | 'broad_group' | 'none') for a detailed SOC in one area."""
    for code, how in ((soc, "exact"), (broad(soc), "broad_group")):
        e = entries.get((fips, code))
        r = e.get("row") if isinstance(e, dict) else None
        if r:
            return r, how
    return None, "none"


class Result:
    def __init__(self, entries: dict, stale: bool, url: str, retrieved_at: str, dropped: int):
        self.entries, self.stale, self.url, self.retrieved_at, self.dropped = entries, stale, url, retrieved_at, dropped


def _file(horizon: str, fips: str) -> str:
    return f"pc-{horizon}-{fips}.json"


def _fresh(entry: dict) -> bool:
    try:
        return datetime.now(UTC) - datetime.fromisoformat(entry["fetched"]) < timedelta(days=TTL_DAYS)
    except (KeyError, ValueError, TypeError):
        return False


async def get(guard: Guard, horizon: str, fips_list: list[str], socs: list[str]) -> Result:
    """Rows for each (area, occupation), reading a per-area cache and fetching only what is missing or expired in batches."""
    codes = request_codes(socs)
    files = {f: (cache.read(_file(horizon, f)) or {"data": {}})["data"] for f in fips_list}
    need = [c for c in codes if any(not _fresh(files[f].get(c, {})) for f in fips_list)]
    stale, dropped, first_url = False, 0, f"{BASE}/{ENDPOINT[horizon]}"
    now = datetime.now(UTC).isoformat(timespec="seconds")
    try:
        for i in range(0, len(need), BATCH):
            batch = need[i:i + BATCH]
            url = f"{BASE}/{ENDPOINT[horizon]}/{'+'.join(fips_list)}/{'+'.join(batch)}"
            try:
                data, public = await guard.get_json(url, params={"items_per_page": "1000"}, max_bytes=4_000_000)
                first_url = public if i == 0 else first_url
            except NotFound:
                data = {"rows": [], "pager": {"total_pages": 1}}  # the API answers 404 'No results found.' when nothing matches
            if not isinstance(data, dict) or not isinstance(data.get("rows"), list) or not isinstance(data.get("pager"), dict):
                raise UpstreamError("public.projectionscentral.org returned an unexpected response.")
            if int(data["pager"].get("total_pages") or 1) > 1:
                raise UpstreamError("public.projectionscentral.org returned more pages than expected.")
            want_fips = {str(int(f)) for f in fips_list}
            found: dict[tuple[str, str], dict] = {}
            for raw in data["rows"]:
                r = row(raw)
                if r is None or r["fips"] not in want_fips or r["soc"] not in batch:
                    dropped += 1
                    continue
                found[(r["fips"], r["soc"])] = r
            for f in fips_list:
                for c in batch:
                    files[f][c] = {"row": found.get((str(int(f)), c)), "fetched": now}
        if need:
            for f in fips_list:
                cache.write(_file(horizon, f), files[f], f"{horizon}-term projections", first_url)
    except UpstreamError:
        have = all(c in files[f] for f in fips_list for c in codes)
        if not have:
            raise
        stale = True
    entries = {}
    for f in fips_list:
        for c in codes:
            entries[(str(int(f)), c)] = files[f].get(c)
    fetched = [e["fetched"] for e in entries.values() if isinstance(e, dict) and e.get("fetched")]
    return Result(entries, stale, first_url, min(fetched) if fetched else now, dropped)
