"""Fill the shared cache with every bulk file the tools need, so the hosted server never downloads inside a user's request.

Runs at image build time (see the Dockerfile) with HIGHERED_MCPS_CACHE set. It calls the tools themselves, with one public
institution, state, occupation and metro area, so whatever a tool loads is exactly what gets cached. BLS files need
HIGHERED_MCPS_CONTACT (the operator's address). Tools backed by live College Scorecard or FAC lookups are not pre-warmed:
they need no bulk files. Exits non-zero if any bulk load failed, so a cold image is never shipped.
"""
import asyncio
import os
import sys
import time
from pathlib import Path

from highered_accreditation import server as accreditation
from highered_funding import server as funding
from highered_institutions import server as institutions
from highered_labor_market import server as labor_market
from highered_risk import server as risk
from mcp.server.mcpserver.exceptions import ToolError

UNITID = "166027"  # the institution the institutions server already probes to detect published IPEDS years
OPEID = "00215500"
STATE, CIP, SOC, AREA = "MA", "51.38", "29-1141", "14460"
PLAN = [
    (institutions, "resolve_institution", {"query": UNITID}),
    (institutions, "compare_peers", {"unitid": UNITID}),
    (institutions, "get_enrollment_trend", {"unitid": UNITID}),
    (institutions, "get_retention", {"unitid": UNITID}),
    (institutions, "get_financial_snapshot", {"unitid": UNITID, "years": 2}),
    (risk, "get_title_iv_status", {"opeid": OPEID}),
    (accreditation, "get_accreditation_status", {"unitid": UNITID}),
    (funding, "get_research_spend", {"unitid": UNITID}),
    (funding, "get_state_funding", {"state": STATE}),
    (funding, "get_enrollment_projection", {"state": STATE}),
    (labor_market, "map_program_to_occupations", {"cip": CIP}),
    (labor_market, "get_occupation_outlook", {"soc": SOC}),
    (labor_market, "get_wages", {"soc": SOC, "state": STATE}),
    (labor_market, "get_wages", {"soc": SOC, "area_code": AREA}),
    (labor_market, "get_occupation_skills", {"soc": SOC}),
    (labor_market, "get_state_occupation_outlook", {"state": STATE, "soc": SOC}),
]
ATTEMPTS = 4


async def _settle(part) -> None:
    """Wait for the part's background downloads (jobs that outlived a tool's deadline) to finish."""
    running = getattr(getattr(part, "bounded", None), "_running", {})
    pending = [t for t in list(running.values()) if not t.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def warm(part, name: str, args: dict) -> tuple[bool, float, str]:
    """Call one tool until it answers without a 'still downloading' error. Returns (ok, seconds, note)."""
    t0 = time.monotonic()
    note = ""
    for _ in range(ATTEMPTS):
        try:
            result = await part.mcp.call_tool(name, args)
            is_error = bool(getattr(result, "isError", False))
            content = getattr(result, "content", None) or []
            text = getattr(content[0], "text", "") if content else ""
        except ToolError as e:  # a tool's own safe-to-show failure; anything else is a bug and should stop the build
            is_error, text = True, str(e)
        await _settle(part)
        if not is_error:
            return True, time.monotonic() - t0, ""
        note = text[:160].replace("\n", " ")
        if "background" not in text and "shortly" not in text:
            break
    return False, time.monotonic() - t0, note


async def run() -> int:
    failed = 0
    for part, name, args in PLAN:
        ok, secs, note = await warm(part, name, args)
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {part.mcp.name:<24} {name:<30} {secs:6.1f}s {note}", file=sys.stderr, flush=True)
    root = os.environ.get("HIGHERED_MCPS_CACHE")
    if root:
        size = sum(p.stat().st_size for p in Path(root).rglob("*") if p.is_file())
        print(f"cache {root}: {size / 1e6:.1f} MB", file=sys.stderr)
    return failed


def main() -> None:
    if not os.environ.get("HIGHERED_MCPS_CONTACT"):
        sys.exit("Set HIGHERED_MCPS_CONTACT (the operator's contact address for BLS) before pre-warming.")
    failed = asyncio.run(run())
    if failed:
        sys.exit(f"{failed} bulk load(s) failed; not shipping a cold cache.")


if __name__ == "__main__":
    main()
