"""Opt-in: HIGHERED_LIVE=1 (+ COLLEGE_SCORECARD_API_KEY). Hits real upstreams."""
import pytest

from highered_institutions import server as s

pytestmark = pytest.mark.live


async def test_live_Test College A(tmp_path, monkeypatch):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    s.set_guard(None)
    d = (await s.resolve_institution("Test Community College A"))["data"]
    assert d["resolved"] and d["candidates"][0]["unitid"] == "999001"
    t = await s.get_enrollment_trend("999001")
    assert any(r[1] for r in t["data"]["rows"])
    c = await s.compare_peers("999001")
    assert len(c["data"]["peers"]) == 5
