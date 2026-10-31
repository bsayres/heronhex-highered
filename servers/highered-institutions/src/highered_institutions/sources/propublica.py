"""ProPublica Nonprofit Explorer API v2. Per-EIN lookups only; nothing is cached or redistributed.

Only organization-level financial summary fields are returned. Officer/employee
compensation fields are deliberately dropped.
"""
from ..http import Guard, NotFound

BASE = "https://projects.propublica.org/nonprofits/api/v2/organizations"
SOURCE = "ProPublica Nonprofit Explorer (IRS Form 990 data). Cite ProPublica."
ORG_FIELDS = ("ein", "name", "city", "state", "ntee_code", "subsection_code", "tax_period")
FILING_FIELDS = ("tax_prd_yr", "formtype", "totrevenue", "totfuncexpns", "totassetsend", "totliabend", "totnetassetend")


async def fetch(guard: Guard, ein: str, max_filings: int = 5) -> tuple[dict | None, str]:
    try:
        data, url = await guard.get_json(f"{BASE}/{ein}.json")
    except NotFound:
        return None, f"{BASE}/{ein}.json"
    org = data.get("organization") or {}
    filings = [
        {k: f.get(k) for k in FILING_FIELDS} for f in (data.get("filings_with_data") or [])[:max_filings]
    ]
    return {"organization": {k: org.get(k) for k in ORG_FIELDS}, "filings": filings}, url
