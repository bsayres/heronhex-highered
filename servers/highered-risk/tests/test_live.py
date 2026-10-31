"""Opt-in: HIGHERED_LIVE=1. Hits real FSA hosts (paced at 7 s/request for studentaid.gov)."""
import pytest

from highered_risk import server as s

pytestmark = pytest.mark.live


async def test_live_fsa(tmp_path, monkeypatch):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    s.set_guard(None)
    r = await s.get_fsa_status("00100200")  # Alabama A&M: on the HCM list when this was written
    assert r["data"]["heightened_cash_monitoring"]["as_of"]
    assert r["data"]["cohort_default_rates"]["entries"]
    r = await s.get_fsa_status("09990100")  # Test College A: public, not scored
    assert r["data"]["financial_responsibility"] is None and r["nulls"]


async def test_live_fac(tmp_path, monkeypatch):
    import os
    if not os.environ.get("FAC_API_KEY"):
        pytest.skip("FAC_API_KEY not set")
    s.set_guard(None)
    r = await s.get_audit_findings(ein="999000001", years=3)  # Test College A
    assert r["data"]["audits"] and all(a["report_url"] for a in r["data"]["audits"])
