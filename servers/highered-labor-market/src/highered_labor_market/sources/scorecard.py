"""College Scorecard field-of-study (program-level) data via the schools endpoint. Key in the X-Api-Key header only."""
import os

from ..http import Guard, UpstreamError

URL = "https://api.data.gov/ed/collegescorecard/v1/schools"
SOURCE = "College Scorecard field-of-study data (U.S. Department of Education)"
KEY_VAR = "COLLEGE_SCORECARD_API_KEY"
P = "latest.programs.cip_4_digit"
FIELDS = ["id", "school.name", f"{P}.code", f"{P}.title", f"{P}.credential.level", f"{P}.credential.title", f"{P}.counts.ipeds_awards1",
          f"{P}.counts.ipeds_awards2", f"{P}.earnings.1_yr.overall_median_earnings", f"{P}.earnings.1_yr.overall_median_earnings_national"]


def has_key() -> bool:
    return bool(os.environ.get(KEY_VAR))


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
    key = os.environ.get(KEY_VAR)
    if not key:
        raise KeyError(KEY_VAR)
    data, url = await guard.get_json(URL, params={"id": unitid, "fields": ",".join(FIELDS)}, headers={"X-Api-Key": key}, max_bytes=10_000_000)
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        raise UpstreamError("api.data.gov returned an unexpected response.")
    if not results:
        return None, url
    r = results[0]
    progs = [x for p in (r.get(P) or []) if (x := _program(p))]
    return {"name": r.get("school.name"), "programs": progs}, url
