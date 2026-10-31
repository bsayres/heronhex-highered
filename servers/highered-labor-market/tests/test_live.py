"""Opt-in: HIGHERED_LIVE=1. Needs HIGHERED_MCPS_CONTACT and COLLEGE_SCORECARD_API_KEY. Downloads about 16 MB of O*NET CSVs on a cold cache."""
import os

import pytest

from highered_labor_market import server as s

pytestmark = pytest.mark.live


async def test_live_all_sources(tmp_path, monkeypatch):
    if not (os.environ.get("HIGHERED_MCPS_CONTACT") and os.environ.get("COLLEGE_SCORECARD_API_KEY")):
        pytest.skip("HIGHERED_MCPS_CONTACT and COLLEGE_SCORECARD_API_KEY are required")
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    s.set_guard(None)
    r = await s.map_program_to_occupations("51.3801")
    assert [x[0] for x in r["data"]["rows"]] == ["25-1072", "29-1141"]
    r = await s.get_occupation_outlook("29-1141")
    assert r["data"]["outlook"]["annual_openings"] > 0 and r["data"]["outlook"]["entry_education"]
    r = await s.get_occupation_skills("29-1141", top=3)
    assert r["data"]["essential_skills"]["rows"] and "CC BY 4.0" in r["citation"]
    r = await s.get_program_outcomes("999001", limit=5)  # Test College A
    assert r["data"]["rows"]
    r = await s.get_program_alignment("999001", "51.38", 2)
    assert r["data"]["openings_summary"]["annual_openings_all_mapped"] > 0
