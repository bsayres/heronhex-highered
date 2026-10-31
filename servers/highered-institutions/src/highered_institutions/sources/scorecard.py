"""College Scorecard API. Key via env var, sent as a header (never in the URL)."""
import os

from ..http import Guard

URL = "https://api.data.gov/ed/collegescorecard/v1/schools"
SOURCE = "U.S. Department of Education College Scorecard"
KEY_VAR = "COLLEGE_SCORECARD_API_KEY"
FIELDS = {
    "ope6_id": "ope6_id",
    "ope8_id": "ope8_id",
    "school.main_campus": "main_campus",
    "school.operating": "operating",
    "school.ownership": "ownership_code",
    "school.degrees_awarded.predominant": "predominant_degree_code",
    "latest.student.size": "undergraduate_size",
    "latest.cost.avg_net_price.overall": "avg_net_price",
    "latest.cost.tuition.in_state": "tuition_in_state",
    "latest.aid.pell_grant_rate": "pell_grant_rate",
    "latest.completion.completion_rate_4yr_150nt": "completion_rate_4yr_150pct",
    "latest.completion.completion_rate_less_than_4yr_150nt": "completion_rate_lt4yr_150pct",
    "latest.earnings.10_yrs_after_entry.median": "median_earnings_10yr",
    "latest.aid.median_debt.completers.overall": "median_debt_completers",
}


def has_key() -> bool:
    return bool(os.environ.get(KEY_VAR))


async def fetch(guard: Guard, unitid: str) -> tuple[dict | None, str]:
    key = os.environ.get(KEY_VAR)
    if not key:
        raise KeyError(KEY_VAR)
    data, url = await guard.get_json(
        URL,
        params={"id": unitid, "fields": ",".join(["id", *FIELDS])},
        headers={"X-Api-Key": key},
    )
    results = data.get("results") or []
    if not results:
        return None, url
    row = results[0]
    return {FIELDS[k]: row.get(k) for k in FIELDS}, url
