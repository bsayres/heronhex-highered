"""NSF Award Search API. Exact match on the awardee's UEI.

The API ignores field selection and returns every field, including PI and co-PI names and emails and
program-officer contact details. Records are projected to the fields below; person fields are never kept.
"""
import re

from ..http import Guard, UpstreamError

URL = "https://api.nsf.gov/services/v1/awards.json"
SOURCE = "NSF Award Search API"
KEEP = {"id": "id", "title": "title", "awardeeName": "awardee", "awardeeStateCode": "state", "date": "award_date",
        "startDate": "start_date", "expDate": "end_date", "fundsObligatedAmt": "obligated_usd", "estimatedTotalAmt": "estimated_total_usd",
        "fundProgramName": "program", "cfdaNumber": "aln", "transType": "award_type", "ueiNumber": "uei", "parentUeiNumber": "parent_uei"}
MONEY = {"fundsObligatedAmt", "estimatedTotalAmt"}
ID_RE = re.compile(r"^[0-9]{4,10}\Z")
PAGE = 25  # API maximum per page


def _project(a: dict) -> dict | None:
    if not ID_RE.match(str(a.get("id", ""))):
        return None
    out = {}
    for k, name in KEEP.items():
        v = a.get(k)
        if k in MONEY:
            v = int(v) if str(v or "").isdigit() else None
        out[name] = v if v != "" else None
    out["url"] = f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={out['id']}"
    return out


async def fetch(guard: Guard, uei: str, limit: int, awarded_from: str | None, awarded_to: str | None) -> dict:
    awards, total, first_url, dropped = [], 0, None, 0
    for offset in range(0, limit, PAGE):
        params = {"ueiNumber": uei, "rpp": str(min(PAGE, limit - offset)), "offset": str(offset + 1)}
        if awarded_from:
            params["dateStart"] = awarded_from
        if awarded_to:
            params["dateEnd"] = awarded_to
        data, url = await guard.get_json(URL, params=params, max_bytes=8_000_000)
        first_url = first_url or url
        resp = data.get("response") if isinstance(data, dict) else None
        if not isinstance(resp, dict) or "serviceNotification" in resp:
            raise UpstreamError("api.nsf.gov rejected the request or returned an unexpected response.")
        total = int((resp.get("metadata") or {}).get("totalCount") or 0)
        page = resp.get("award") or []
        for a in page:
            p = _project(a)
            if p is None:
                dropped += 1
            else:
                awards.append(p)
        if len(page) < int(params["rpp"]) or offset + PAGE >= total:
            break
    return {"awards": awards[:limit], "total": total, "url": first_url, "dropped": dropped}
