"""Grants.gov opportunity search (open or forecasted funding opportunities, not awards)."""
import html
import re

from ..http import Guard, UpstreamError

URL = "https://api.grants.gov/v1/api/search2"
SOURCE = "Grants.gov Search API (funding opportunities, not awards)"
ELIGIBILITY = {"public_ihe": "06", "private_ihe": "20", "any": ""}
ID_RE = re.compile(r"^[0-9]{1,12}\Z")


def _text(v):
    """Grants.gov sends titles with HTML entities (&rsquo;, &ndash;). Decoded to plain text; still untrusted and never put in markup."""
    return html.unescape(v) if isinstance(v, str) else v


def _hit(h: dict) -> dict | None:
    if not ID_RE.match(str(h.get("id", ""))):
        return None
    return {
        "opportunity_number": h.get("number"), "title": _text(h.get("title")), "agency": _text(h.get("agency")), "agency_code": h.get("agencyCode"),
        "status": h.get("oppStatus"), "open_date": h.get("openDate"), "close_date": h.get("closeDate"),
        "aln": h.get("cfdaList") or [], "url": f"https://www.grants.gov/search-results-detail/{h['id']}",
    }


async def search(guard: Guard, keyword: str | None, statuses: list[str], eligibility: str, agency: str | None, rows: int) -> dict:
    body = {"oppStatuses": "|".join(statuses), "rows": rows, "sortBy": "openDate|desc"}
    if keyword:
        body["keyword"] = keyword
    if ELIGIBILITY[eligibility]:
        body["eligibilities"] = ELIGIBILITY[eligibility]
    if agency:
        body["agencies"] = agency
    data, url = await guard.post_json(URL, body, max_bytes=8_000_000)
    d = data.get("data") if isinstance(data, dict) else None
    if not isinstance(d, dict) or data.get("errorcode") != 0 or not isinstance(d.get("oppHits"), list):
        raise UpstreamError("api.grants.gov returned an unexpected response.")
    hits = [x for h in d["oppHits"] if (x := _hit(h))]
    return {"opportunities": hits, "total": int(d.get("hitCount") or 0), "url": url}
