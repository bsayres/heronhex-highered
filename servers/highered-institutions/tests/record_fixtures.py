"""Re-record small fixtures from live APIs (dev tool; not run in CI).

Usage: PYTHONPATH=src COLLEGE_SCORECARD_API_KEY=... python tests/record_fixtures.py
Only response bodies are stored; the API key travels in a header and never appears in them.
"""
import asyncio
import json
from pathlib import Path

from highered_institutions.http import Guard
from highered_institutions.sources import scorecard, urban

OUT = Path(__file__).parent / "fixtures"
IDS = {  # target, its live top peers, shared-name and shared-OPEID cases, one private nonprofit, distractors
    "999001", "206446", "187666", "233903", "172307", "189194", "999004", "166027",
    "112561", "177065", "217934", "455983", "139579", "475121", "101116",
}
YEARS = range(2015, 2025)


async def main():
    g = Guard()
    year = await urban.latest_year(g)
    d = await urban.directory(g, year)
    rows = [r for r in d.data if str(r["unitid"]) in IDS]
    (OUT / "directory.json").write_text(json.dumps({"year": year, "results": rows}, indent=1))
    enr = {}
    for y in YEARS:
        t = (await urban.enrollment_totals(g, y)).data
        enr[str(y)] = {u: t.get(u) for u in IDS}
    (OUT / "enrollment.json").write_text(json.dumps(enr, indent=1))
    sc, _ = await g.get_json(scorecard.URL, {"id": "999001", "fields": ",".join(["id", *scorecard.FIELDS])}, {"X-Api-Key": __import__("os").environ["COLLEGE_SCORECARD_API_KEY"]})
    (OUT / "scorecard_999001.json").write_text(json.dumps(sc, indent=1))
    fin = {}
    for u in ("999001", "166027"):
        row, _ = await urban.finance(g, u, 2023)
        fin[u] = {"unitid": int(u), "year": 2023, **row}
    (OUT / "finance_2023.json").write_text(json.dumps(fin, indent=1))
    await g.aclose()


asyncio.run(main())
