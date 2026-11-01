"""College Scorecard field-of-study (program-level) data via the schools endpoint. Key in the X-Api-Key header only."""
import os

from ..http import Guard, UpstreamError

URL = "https://api.data.gov/ed/collegescorecard/v1/schools"
SOURCE = "College Scorecard field-of-study data (U.S. Department of Education)"
KEY_VAR = "COLLEGE_SCORECARD_API_KEY"
P = "latest.programs.cip_4_digit"
FIELDS = ["id", "school.name", f"{P}.code", f"{P}.title", f"{P}.credential.level", f"{P}.credential.title", f"{P}.counts.ipeds_awards1",
          f"{P}.counts.ipeds_awards2", f"{P}.earnings.1_yr.overall_median_earnings", f"{P}.earnings.1_yr.overall_median_earnings_national"]


DEMO_KEY = "DEMO_KEY"  # api.data.gov's public shared key; heavily rate limited, so only a fallback for first runs
DEMO_NOTE = (f"{KEY_VAR} is not set, so this call used api.data.gov's shared DEMO_KEY, which allows only about 10 requests before it is blocked. "
             "Get a free key at https://api.data.gov/signup and set it in the server environment for normal use.")


def api_key() -> str:
    return os.environ.get(KEY_VAR) or DEMO_KEY


def using_demo_key() -> bool:
    return not os.environ.get(KEY_VAR)


def _int(v) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _program(p: dict) -> dict | None:
    code = str(p.get("code") or "").zfill(4)
    cred = (p.get("credential") or {}).get("level")
    if not (code.isdigit() and len(code) == 4 and isinstance(cred, int) and 1 <= cred <= 8):
        return None
    e1 = (p.get("earnings") or {}).get("1_yr") or {}
    c = p.get("counts") or {}
    return {"cip4": f"{code[:2]}.{code[2:]}", "title": p.get("title"), "credential_level": cred, "awards_period_1": _int(c.get("ipeds_awards1")),
            "awards_period_2": _int(c.get("ipeds_awards2")), "earnings_1yr_median_institution": _int(e1.get("overall_median_earnings")),
            "earnings_1yr_median_national": _int(e1.get("overall_median_earnings_national"))}


async def fetch(guard: Guard, unitid: str) -> tuple[dict | None, str]:
    data, url = await guard.get_json(URL, params={"id": unitid, "fields": ",".join(FIELDS)}, headers={"X-Api-Key": api_key()}, max_bytes=10_000_000)
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        raise UpstreamError("api.data.gov returned an unexpected response.")
    if not results:
        return None, url
    r = results[0]
    progs = [x for p in (r.get(P) or []) if (x := _program(p))]
    return {"name": r.get("school.name"), "programs": progs}, url


PAGE_SIZE = 100
MAX_PAGES = 15
F = "latest.programs.cip_4_digit"
OFFER_FIELDS = ["id", "school.name", "school.city", "school.state", f"{F}.code", f"{F}.credential.level", f"{F}.counts.ipeds_awards1",
                f"{F}.counts.ipeds_awards2", f"{F}.earnings.1_yr.overall_median_earnings", f"{F}.earnings.1_yr.overall_median_earnings_national"]


async def offerings(guard: Guard, cip4: str, credential: int, state: str | None) -> tuple[list[dict], int, bool, str]:
    """Institutions that report awards in one 4-digit CIP at one credential level (optionally in one state).
    Returns (rows, total reported by the API, complete, url). `complete` is False when MAX_PAGES was reached first."""
    rows: list[dict] = []
    total, url = 0, URL
    for page in range(MAX_PAGES):
        params = {f"{F}.code": cip4.replace(".", ""), f"{F}.credential.level": str(credential), "_per_page": str(PAGE_SIZE),
                  "_page": str(page), "_fields": ",".join(OFFER_FIELDS)}
        if state:
            params["school.state"] = state
        data, url = await guard.get_json(URL, params=params, headers={"X-Api-Key": api_key()}, max_bytes=10_000_000)
        results = data.get("results") if isinstance(data, dict) else None
        meta = data.get("metadata") if isinstance(data, dict) else None
        if not isinstance(results, list) or not isinstance(meta, dict) or not isinstance(meta.get("total"), int):
            raise UpstreamError("api.data.gov returned an unexpected response.")
        total = meta["total"]
        for r in results:
            prog = next((x for x in (r.get(F) or []) if _program(x) and _program(x)["cip4"] == cip4 and _program(x)["credential_level"] == credential), None)
            uid = str(r.get("id") or "")
            if prog is None or not (uid.isdigit() and len(uid) == 6):
                continue
            p = _program(prog)
            rows.append({"unitid": uid, "name": r.get("school.name"), "city": r.get("school.city"), "state": r.get("school.state"),
                         "awards_period_1": p["awards_period_1"], "awards_period_2": p["awards_period_2"],
                         "earnings_1yr_median_institution": p["earnings_1yr_median_institution"],
                         "earnings_1yr_median_national": p["earnings_1yr_median_national"]})
        if (page + 1) * PAGE_SIZE >= total:
            return rows, total, True, url
        if not results:  # the API said there were more, but gave none: do not claim the list is whole
            return rows, total, False, url
    return rows, total, False, url
