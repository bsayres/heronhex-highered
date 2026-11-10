"""Opt-in: HIGHERED_LIVE=1. Hits real FSA hosts (paced at 7 s/request for studentaid.gov)."""
import os

import pytest

from highered_risk import server as s

pytestmark = pytest.mark.live


async def test_live_fsa(tmp_path, monkeypatch):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    s.set_guard(None)
    r = await s.get_title_iv_status("00100200")  # Alabama A&M: on the HCM list when this was written
    assert r["data"]["heightened_cash_monitoring"]["as_of"]
    assert r["data"]["cohort_default_rates"]["entries"]
    if os.environ.get("HIGHERED_LIVE_OPEID"):
        r = await s.get_title_iv_status(os.environ["HIGHERED_LIVE_OPEID"])
        assert "financial_responsibility" in r["data"]


async def test_live_fac(tmp_path, monkeypatch):
    if not (os.environ.get("FAC_API_KEY") and os.environ.get("HIGHERED_LIVE_UEI")):
        pytest.skip("FAC_API_KEY and HIGHERED_LIVE_UEI not set")
    s.set_guard(None)
    r = await s.get_audit_findings(uei=os.environ["HIGHERED_LIVE_UEI"], years=3)
    assert r["data"]["audits"] and all(a["report_url"] for a in r["data"]["audits"])
