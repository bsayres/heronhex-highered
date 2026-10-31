"""NIH RePORTER v2 project search.

RePORTER has no UEI search criterion (an unknown criterion is silently ignored and returns everything), so the query is
by organization name and every returned row is kept only if its own `org_ueis` contains one of the institution's UEIs.
"""
from ..http import Guard, UpstreamError

URL = "https://api.reporter.nih.gov/v2/projects/search"
SOURCE = "NIH RePORTER"
FIELDS = ["ApplId", "ProjectNum", "ProjectTitle", "FiscalYear", "AwardAmount", "Organization", "AgencyIcAdmin",
          "ProjectStartDate", "ProjectEndDate", "ActivityCode"]
PAGE = 500


def _project(r: dict, ueis: set[str]) -> dict | None:
    org = r.get("organization") or {}
    if not ueis & set(org.get("org_ueis") or []):
        return None
    appl = r.get("appl_id")
    ic = r.get("agency_ic_admin") or {}
    return {
        "project_number": r.get("project_num"), "title": r.get("project_title"), "fiscal_year": r.get("fiscal_year"),
        "award_amount_usd": r.get("award_amount"), "activity_code": r.get("activity_code"),
        "institute": ic.get("abbreviation"), "organization": org.get("org_name"), "organization_ueis": org.get("org_ueis"),
        "start_date": (r.get("project_start_date") or "")[:10] or None, "end_date": (r.get("project_end_date") or "")[:10] or None,
        "url": f"https://reporter.nih.gov/project-details/{appl}" if isinstance(appl, int) else None,
    }


async def fetch(guard: Guard, name: str, ueis: set[str], fiscal_year: int, limit: int) -> dict:
    body = {"criteria": {"org_names": [name], "fiscal_years": [fiscal_year]}, "include_fields": FIELDS,
            "offset": 0, "limit": PAGE, "sort_field": "award_amount", "sort_order": "desc"}
    data, url = await guard.post_json(URL, body, max_bytes=8_000_000)
    if not isinstance(data, dict) or not isinstance(data.get("results"), list) or not isinstance(data.get("meta"), dict):
        raise UpstreamError("api.reporter.nih.gov returned an unexpected response.")
    total = int(data["meta"].get("total") or 0)
    rows = [p for r in data["results"] if (p := _project(r, ueis))]
    return {"projects": rows[:limit], "name_matches_total": total, "name_matches_examined": len(data["results"]),
            "verified_found": len(rows), "url": url, "complete": total <= len(data["results"])}

