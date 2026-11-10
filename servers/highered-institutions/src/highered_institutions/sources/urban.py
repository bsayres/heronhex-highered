"""Urban Institute Education Data API (IPEDS). Whole-year tables, cached for a quarter."""
from datetime import UTC, datetime

from .. import cache
from ..http import BULK_TIMEOUT, Guard, NotFound, UpstreamError

BASE = "https://educationdata.urban.org/api/v1/college-university/ipeds"
# Year probes ask for one large institution that reports every year, so the answer says whether a year is published.
PROBE_UNITID = "166027"
SOURCE = "IPEDS via Urban Institute Education Data Portal (ODC-By 1.0)"

# Personal data (e.g. chief administrator name) is deliberately not kept.
DIRECTORY_FIELDS = ["unitid", "inst_name", "inst_alias", "city", "state_abbr", "opeid", "ein", "ueis", "url_school", "inst_control", "institution_level", "sector", "degree_granting", "currently_active_ipeds", "date_closed", "newid", "inst_system_flag", "inst_system_name", "offering_highest_level", "hbcu", "tribal_college", "cc_basic_2025", "cc_basic_2021", "cc_research_act_desig_2025", "cc_instit_size_2025", "cc_size_setting_2021", "cbsa", "county_fips"]


class Cached:
    def __init__(self, data, meta: dict, stale: bool):
        self.data, self.meta, self.stale = data, meta, stale


async def _paged(guard: Guard, url: str, params: dict, max_bytes: int) -> tuple[list, str]:
    rows: list = []
    first_url = None
    for _page in range(10):
        data, public = await guard.get_json(url, params=params, max_bytes=max_bytes, timeout=BULK_TIMEOUT)
        first_url = first_url or public
        rows.extend(data.get("results", []))
        nxt = data.get("next")
        if not nxt:
            return rows, first_url
        url, params = nxt, None  # guard re-checks the host of `next`
    raise UpstreamError("Too many pages from Urban API.")


async def _cached(guard: Guard, name: str, fetch, ttl_days: int = cache.TTL_DAYS, valid=None) -> Cached:
    """Cache (quarterly for whole-year tables, a day for single-institution rows). If a refresh fails, serve the stale copy and say so."""
    hit = cache.read(name)
    if hit and valid is not None and not valid(hit["data"]):
        stale_copy, hit = hit, None  # a cache written by an older version lacks fields we now need: fetch again
    else:
        stale_copy = None
    if hit and cache.is_fresh(hit["meta"], ttl_days):
        return Cached(hit["data"], hit["meta"], False)
    try:
        data, as_of, url = await fetch()
    except UpstreamError:
        if hit or stale_copy:
            keep = hit or stale_copy
            return Cached(keep["data"], keep["meta"], True)
        raise
    return Cached(data, cache.write(name, data, as_of, url), False)


async def latest_year(guard: Guard) -> int:
    """Newest year with directory data (probes at most 3 years back from today)."""
    async def fetch():
        this = datetime.now(UTC).year
        for year in range(this, this - 3, -1):
            try:
                data, url = await guard.get_json(f"{BASE}/directory/{year}/", {"unitid": PROBE_UNITID})
            except NotFound:
                continue
            if data.get("count"):
                return {"year": year}, f"IPEDS directory {year}", url
        raise UpstreamError("Could not determine the latest IPEDS year.")

    return (await _cached(guard, "urban-latest-year.json", fetch)).data["year"]


async def directory(guard: Guard, year: int) -> Cached:
    async def fetch():
        rows, url = await _paged(guard, f"{BASE}/directory/{year}/", {"fields": ",".join(DIRECTORY_FIELDS)}, 40_000_000)  # fields: 14 MB of columns we never read becomes under 1 MB
        slim = [{k: r.get(k) for k in DIRECTORY_FIELDS} for r in rows]
        return slim, f"IPEDS directory {year}", url

    return await _cached(guard, f"urban-directory-{year}.json", fetch, valid=lambda rows: bool(rows) and "cbsa" in rows[0])


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
                data, url = await guard.get_json(f"{BASE}/fall-enrollment/{year}/99/", {"unitid": PROBE_UNITID, "sex": 99, "race": 99, "ftpt": 99}, attempts=1)
            except UpstreamError:  # Urban answers HTTP 500 (not 404) for a year not yet published
                continue
            if data.get("count"):
                return {"year": year}, f"IPEDS fall enrollment {year}", url
        raise UpstreamError("Could not determine the latest IPEDS enrollment year.")

    return (await _cached(guard, "urban-latest-enrollment-year.json", fetch)).data["year"]


FINANCE_FIELDS = [
    "rev_total_current", "exp_total_current", "assets", "liabilities", "net_position_end", "equity_end",
    "rev_tuition_fees_net", "rev_appropriations_state", "rev_grants_contracts_federal", "exp_instruc_total",
    "endowment_end", "longterm_debt", "est_fte", "form_type", "reporting_form",
    "rev_operating", "rev_nonoperating", "rev_additions", "rev_capital_approps", "net_position_change",
]


async def latest_finance_year(guard: Guard, directory_year: int) -> int:
    """Newest year with finance data (published later than the directory)."""
    async def fetch():
        for year in range(directory_year, directory_year - 4, -1):
            try:
                data, url = await guard.get_json(f"{BASE}/finance/{year}/", {"unitid": PROBE_UNITID}, attempts=1)
            except UpstreamError:
                continue
            if data.get("count"):
                return {"year": year}, f"IPEDS finance {year}", url
        raise UpstreamError("Could not determine the latest IPEDS finance year.")

    return (await _cached(guard, "urban-latest-finance-year.json", fetch)).data["year"]


async def finance(guard: Guard, unitid: str, year: int) -> tuple[dict | None, str]:
    """One institution's finance row for one year (small request, cached for a day)."""
    async def fetch():
        data, url = await guard.get_json(f"{BASE}/finance/{year}/", {"unitid": unitid})
        rows = data.get("results") or []
        return ({k: rows[0].get(k) for k in FINANCE_FIELDS} if rows else None), f"IPEDS finance {year}", url

    c = await _cached(guard, f"urban-finance-{unitid}-{year}.json", fetch, ttl_days=1)
    return c.data, c.meta["source_url"]


async def enrollment_one(guard: Guard, unitid: str, year: int) -> Cached:
    """One institution's fall headcount (all students) for one year, as {unitid: value}. Uses the whole-year table when it is cached,
    otherwise a single small request (cached for a day), so a first call does not download every institution's data."""
    bulk = cache.read(f"urban-fall-enrollment-total-{year}.json")
    if bulk and cache.is_fresh(bulk["meta"]):
        return Cached({unitid: bulk["data"].get(unitid)}, bulk["meta"], False)

    async def fetch():
        params = {"unitid": unitid, "sex": 99, "race": 99, "ftpt": 99, "class_level": 99, "degree_seeking": 99}
        data, url = await guard.get_json(f"{BASE}/fall-enrollment/{year}/99/", params)
        mine = [r for r in data.get("results") or [] if str(r.get("unitid")) == unitid]
        return {unitid: mine[0].get("enrollment_fall") if mine else None}, f"IPEDS fall enrollment {year}", url

    return await _cached(guard, f"urban-enrollment-{unitid}-{year}.json", fetch, ttl_days=1)
