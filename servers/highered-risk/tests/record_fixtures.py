"""Re-record FAC fixtures from the live API (needs FAC_API_KEY). Keeps only the fields the server requests."""
import asyncio
import json
from pathlib import Path

from highered_risk.http import Guard
from highered_risk.sources import fac

OUT = Path(__file__).parent / "fixtures"
import os

EIN = os.environ["HIGHERED_LIVE_EIN"]  # the institution to record; replace names and ids before committing (see testing.md)


async def main() -> None:
    import os
    key = {"X-Api-Key": os.environ[fac.KEY_VAR]}
    g = Guard()
    gen, _ = await g.get_json(f"{fac.BASE}/general", params={"auditee_ein": f"eq.{EIN}", "select": ",".join(fac.GENERAL_FIELDS), "order": "audit_year.desc", "limit": "2"}, headers=key)
    ids = ",".join(r["report_id"] for r in gen)
    fnd, _ = await g.get_json(f"{fac.BASE}/findings", params={"report_id": f"in.({ids})", "select": ",".join(fac.FINDING_FIELDS)}, headers=key)
    awd, _ = await g.get_json(f"{fac.BASE}/federal_awards", params={"report_id": f"in.({ids})", "findings_count": "gt.0", "select": ",".join(fac.AWARD_FIELDS)}, headers=key)
    (OUT / "fac_college_a.json").write_text(json.dumps({"general": gen, "findings": fnd, "federal_awards": awd}, indent=1))
    await g.aclose()


asyncio.run(main())
