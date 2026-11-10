"""Opt-in: HIGHERED_LIVE=1. Downloads the real DAPIP file once (about 4 MB) into a temporary cache."""
import os

import pytest

from highered_accreditation import server as s

pytestmark = pytest.mark.live

UNITID = os.environ.get("HIGHERED_LIVE_UNITID")  # an institution of your choice; see .env.example


async def test_live_status_and_actions(tmp_path, monkeypatch):
    if not UNITID:
        pytest.skip("HIGHERED_LIVE_UNITID not set")
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    s.set_guard(None)
    r = await s.get_accreditation_status(UNITID)
    d = r["data"]
    assert d["opeid"] and r["as_of"].startswith("actions recorded through 20")
    assert d["summary"]["current_institutional_accreditors"], "an institutional accreditor should be current"
    a = await s.get_accreditation_actions(UNITID)
    assert a["data"]["actions"] and a["data"]["actions"][0]["date"]
    assert (tmp_path / "accreditation" / "dapip.json").exists()
    s.set_guard(None)
