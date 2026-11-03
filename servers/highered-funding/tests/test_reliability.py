"""A slow bulk download answers inside the deadline and finishes in the background; years are fetched at once."""
import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_funding import bounded, server
from highered_funding.sources import herd, sheeo, wiche


async def test_a_herd_year_that_misses_the_deadline_is_a_null_and_the_others_are_returned(upstream, monkeypatch):
    monkeypatch.setattr(bounded, "DEADLINE", 0.2)
    real = herd.year

    async def slow(g, y):
        if y == 2023:
            await asyncio.sleep(0.5)
        return await real(g, y)

    monkeypatch.setattr(herd, "year", slow)
    r = await server.get_research_spend("214777", years=2)
    assert any(n["field"] == "FY2023" and n["kind"] == "source_unavailable" and "time limit" in n["reason"] for n in r["nulls"])
    assert r["data"]["rows"]  # other years returned
    await asyncio.sleep(0.6)
    monkeypatch.setattr(herd, "year", real)
    later = await server.get_research_spend("214777", years=2)
    assert not [n for n in later["nulls"] if n["kind"] == "source_unavailable"]


@pytest.mark.parametrize("mod,call,args,what", [(sheeo, "get_state_funding", ("MA",), "SHEEO"), (wiche, "get_enrollment_projection", ("MA",), "WICHE")])
async def test_first_download_that_runs_past_the_deadline_says_so_and_finishes_later(upstream, monkeypatch, mod, call, args, what):
    monkeypatch.setattr(bounded, "DEADLINE", 0.1)
    real = mod.load

    async def slow(g):
        await asyncio.sleep(0.4)
        return await real(g)

    monkeypatch.setattr(mod, "load", slow)
    with pytest.raises(ToolError, match="downloaded for the first time"):
        await getattr(server, call)(*args)
    await asyncio.sleep(0.6)
    monkeypatch.setattr(bounded, "DEADLINE", 45.0)
    monkeypatch.setattr(mod, "load", real)
    r = await getattr(server, call)(*args)
    assert r["data"]["state"] == "MA"
