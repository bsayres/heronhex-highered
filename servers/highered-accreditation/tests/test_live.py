"""Opt-in: HIGHERED_LIVE=1. Downloads the real DAPIP file once (about 4 MB) into a temporary cache."""
import pytest

from highered_accreditation import server as s

pytestmark = pytest.mark.live


async def test_live_Test College A(tmp_path, monkeypatch):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    s.set_guard(None)
    r = await s.get_accreditation_status("999001")  # Test College A
    d = r["data"]
    assert d["opeid"] == "09990100" and r["as_of"].startswith("actions recorded through 20")
    assert d["summary"]["current_institutional_accreditors"], "an institutional accreditor should be current"
    ended = d["summary"]["not_current_programs"]
    assert ended and all(p["last_action"] for p in ended), "Test College A's ended nursing and radiography records should carry the action that precedes the end"
    a = await s.get_accreditation_actions("999001", scope="programmatic")
    assert a["data"]["counts_by_category"].get("loss") and a["data"]["actions"][0]["date"]
    assert (tmp_path / "accreditation" / "dapip.json").exists()
    s.set_guard(None)
