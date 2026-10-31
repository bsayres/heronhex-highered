"""Urban Institute Education Data API (IPEDS). Whole-year tables, cached for a quarter."""
from datetime import UTC, datetime

from .. import cache
from ..http import Guard, NotFound, UpstreamError

BASE = "https://educationdata.urban.org/api/v1/college-university/ipeds"
SOURCE = "IPEDS via Urban Institute Education Data Portal (ODC-By 1.0)"

# Personal data (e.g. chief administrator name) is deliberately not kept.
DIRECTORY_FIELDS = ["unitid", "inst_name", "inst_alias", "city", "state_abbr", "opeid", "ein", "ueis", "url_school", "inst_control", "institution_level", "sector", "degree_granting", "currently_active_ipeds", "date_closed", "newid", "inst_system_flag", "inst_system_name", "offering_highest_level", "hbcu", "tribal_college", "cc_basic_2025", "cc_basic_2021", "cc_research_act_desig_2025", "cc_instit_size_2025", "cc_size_setting_2021"]


class Cached:
    def __init__(self, data, meta: dict, stale: bool):
        self.data, self.meta, self.stale = data, meta, stale


async def _paged(guard: Guard, url: str, params: dict, max_bytes: int) -> tuple[list, str]:
    rows: list = []
    first_url = None
    for _page in range(10):
        data, public = await guard.get_json(url, params=params, max_bytes=max_bytes)
        first_url = first_url or public
        rows.extend(data.get("results", []))
        nxt = data.get("next")
        if not nxt:
            return rows, first_url
        url, params = nxt, None  # guard re-checks the host of `next`
    raise UpstreamError("Too many pages from Urban API.")


async def _cached(guard: Guard, name: str, fetch) -> Cached:
    """Quarterly cache. If a refresh fails, serve the stale copy and say so."""
    hit = cache.read(name)
    if hit and cache.is_fresh(hit["meta"]):
        return Cached(hit["data"], hit["meta"], False)
    try:
        data, as_of, url = await fetch()
    except UpstreamError:
        if hit:
            return Cached(hit["data"], hit["meta"], True)
        raise
    return Cached(data, cache.write(name, data, as_of, url), False)


async def latest_year(guard: Guard) -> int:
    """Newest year with directory data (probes at most 3 years back from today)."""
    async def fetch():
        this = datetime.now(UTC).year
        for year in range(this, this - 3, -1):
            try:
                data, url = await guard.get_json(f"{BASE}/directory/{year}/", {"unitid": "999001"})
            except NotFound:
                continue
            if data.get("count"):
                return {"year": year}, f"IPEDS directory {year}", url
        raise UpstreamError("Could not determine the latest IPEDS year.")

    return (await _cached(guard, "urban-latest-year.json", fetch)).data["year"]


async def directory(guard: Guard, year: int) -> Cached:
    async def fetch():
        rows, url = await _paged(guard, f"{BASE}/directory/{year}/", {}, 40_000_000)
        slim = [{k: r.get(k) for k in DIRECTORY_FIELDS} for r in rows]
        return slim, f"IPEDS directory {year}", url

    return await _cached(guard, f"urban-directory-{year}.json", fetch)


async def enrollment_totals(guard: Guard, year: int) -> Cached:
    """Fall headcount, all students (every disaggregator = 99), keyed by unitid."""
    async def fetch():
        params = {"sex": 99, "race": 99, "ftpt": 99, "class_level": 99, "degree_seeking": 99}
        rows, url = await _paged(guard, f"{BASE}/fall-enrollment/{year}/99/", params, 10_000_000)
        slim = {str(r["unitid"]): r.get("enrollment_fall") for r in rows}
        return slim, f"IPEDS fall enrollment {year}", url

    return await _cached(guard, f"urban-fall-enrollment-total-{year}.json", fetch)


async def latest_enrollment_year(guard: Guard, directory_year: int) -> int:
    """Newest year with fall-enrollment data (the directory is often published first)."""
    async def fetch():
        for year in range(directory_year, directory_year - 3, -1):
            try:
                data, url = await guard.get_json(f"{BASE}/fall-enrollment/{year}/99/", {"unitid": "999001", "sex": 99, "race": 99, "ftpt": 99}, attempts=1)
            except UpstreamError:  # Urban answers HTTP 500 (not 404) for a year not yet published
                continue
            if data.get("count"):
                return {"year": year}, f"IPEDS fall enrollment {year}", url
        raise UpstreamError("Could not determine the latest IPEDS enrollment year.")

    return (await _cached(guard, "urban-latest-enrollment-year.json", fetch)).data["year"]
