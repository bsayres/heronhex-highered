"""Opt-in: HIGHERED_LIVE=1. Hits real upstream hosts (HERD downloads about 7 MB per year)."""
import pytest

from highered_funding import server as s

pytestmark = pytest.mark.live


async def test_live_all_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    s.set_guard(None)
    r = await s.get_research_spend("214777", years=1)  # Penn State
    assert r["data"]["rows"] and r["data"]["rows"][0][8] > 0
    r = await s.get_research_spend("999001", years=1)  # Test College A: below the HERD threshold
    assert r["data"]["rows"] == [] and r["nulls"]
    r = await s.get_state_funding("MA", start_fy=2024)
    assert r["data"]["rows"] and r["citation"]
    r = await s.get_enrollment_projection("MA")
    assert r["data"]["rows"] and r["license"]
    r = await s.search_grant_awards(["NPM2J7MSCF61"], institution_name="PENNSYLVANIA STATE UNIVERSITY", fiscal_year=2025, limit=3)
    assert r["data"]["nsf"]["awards"] and r["data"]["nih"]["projects"]
    r = await s.search_funding_opportunities(keyword="community college", eligibility="public_ihe", rows=2)
    assert r["data"]["opportunities"]
