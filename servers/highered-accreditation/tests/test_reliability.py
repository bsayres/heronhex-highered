"""The DAPIP file is one large download; a first call that runs past the deadline says so and the download finishes later."""
import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_accreditation import bounded, server
from highered_accreditation.sources import dapip


async def test_first_download_that_runs_past_the_deadline_says_so_and_finishes_later(upstream, monkeypatch):
    monkeypatch.setattr(bounded, "DEADLINE", 0.1)
    real = dapip.load

    async def slow(g):
        await asyncio.sleep(0.4)
        return await real(g)

    monkeypatch.setattr(dapip, "load", slow)
    with pytest.raises(ToolError, match="downloaded for the first time"):
        await server.get_accreditation_status("999001")
    await asyncio.sleep(0.6)
    monkeypatch.setattr(bounded, "DEADLINE", 45.0)
    monkeypatch.setattr(dapip, "load", real)
    r = await server.get_accreditation_status("999001")
    assert r["data"]["name_in_dapip"] == "Test Community College A"
    assert bounded._running == {}  # nothing left running


async def test_two_calls_at_once_share_one_download(upstream):
    a, b = await asyncio.gather(server.get_accreditation_status("999001"), server.get_accreditation_actions("999001"))
    assert a["data"]["unitid"] == b["data"]["unitid"] == "999001"
    downloads = [q for q in upstream.requests if q.method == "POST"]
    assert len(downloads) == 1
