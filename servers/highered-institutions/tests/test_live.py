"""Opt-in: HIGHERED_LIVE=1 (+ COLLEGE_SCORECARD_API_KEY). Hits real upstreams."""
import os

import pytest

from highered_institutions import server as s

pytestmark = pytest.mark.live

NAME = os.environ.get("HIGHERED_LIVE_NAME")  # exact institution name
UNITID = os.environ.get("HIGHERED_LIVE_UNITID")  # its UNITID; see .env.example


async def test_live_resolve_trend_peers(tmp_path, monkeypatch):
    if not (NAME and UNITID):
        pytest.skip("HIGHERED_LIVE_NAME and HIGHERED_LIVE_UNITID not set")
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    s.set_guard(None)
    d = (await s.resolve_institution(NAME))["data"]
    assert d["resolved"] and d["candidates"][0]["unitid"] == UNITID
    t = await s.get_enrollment_trend(UNITID)
    assert any(r[1] for r in t["data"]["rows"])
    c = await s.compare_peers(UNITID)
    assert len(c["data"]["peers"]) == 5
