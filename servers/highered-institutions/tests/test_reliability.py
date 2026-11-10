"""Slow or stalled upstream requests: one deadline per tool call, work that misses it finishes in the background, small
requests are cached for a day and carry a short timeout."""
import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_institutions import bounded, cache, http
from highered_institutions import server as s
from highered_institutions.sources import urban


async def test_bounded_run_returns_what_finished_and_lets_the_rest_finish_in_the_background():
    done = []

    async def quick():
        return "q"

    async def slow():
        await asyncio.sleep(0.3)
        done.append(1)
        return "s"

    async def boom():
        raise RuntimeError("x")

    results, errors, late = await bounded.run({"a": ("job-a", quick), "b": ("job-b", slow), "c": ("job-c", boom)}, seconds=0.05)
    assert results == {"a": "q"} and late == ["b"] and isinstance(errors["c"], RuntimeError) and not done
    await asyncio.sleep(0.4)
    assert done == [1]  # not cancelled
    again, _e, late2 = await bounded.run({"b": ("job-b", slow)}, seconds=1)
    assert again == {"b": "s"} and not late2


async def test_the_same_job_is_shared_not_started_twice():
    calls = []

    async def work():
        calls.append(1)
        await asyncio.sleep(0.1)
        return 1

    r1, r2 = await asyncio.gather(bounded.run({"k": ("same", work)}, seconds=1), bounded.run({"k": ("same", work)}, seconds=1))
    assert r1[0] == r2[0] == {"k": 1} and len(calls) == 1


async def test_finance_rows_are_cached_for_a_day(upstream):
    await s.get_financial_snapshot("999001", years=3)
    n = len([r for r in upstream.requests if "/finance/" in r.url.path])
    await s.get_financial_snapshot("999001", years=3)
    assert len([r for r in upstream.requests if "/finance/" in r.url.path]) == n  # second call made no finance request


async def test_a_stale_finance_row_is_served_when_the_refresh_fails(upstream, monkeypatch):
    first = await s.get_financial_snapshot("999001", years=1)
    monkeypatch.setattr(urban.cache, "is_fresh", lambda meta, ttl_days=cache.TTL_DAYS: False)
    upstream.finance.clear()  # the mock now answers 500 for every finance year, so every refresh fails
    again = await s.get_financial_snapshot("999001", years=1)
    assert again["data"]["figures"] == first["data"]["figures"]


async def test_a_finance_year_that_misses_the_deadline_is_a_null_and_the_rest_are_returned(upstream, monkeypatch):
    monkeypatch.setattr(bounded, "DEADLINE", 0.2)
    real = urban.finance

    async def slow(guard, unitid, year):
        if year == 2022:
            await asyncio.sleep(0.5)
        return await real(guard, unitid, year)

    monkeypatch.setattr(urban, "finance", slow)
    r = await s.get_financial_snapshot("999001", years=3)
    assert [row[0] for row in r["data"]["history"]["rows"]] == [2021, 2023]
    n = next(n for n in r["nulls"] if n["field"] == "FY2022")
    assert n["kind"] == "source_unavailable" and "time limit" in n["reason"] and any("missing" in w for w in r["warnings"])
    await asyncio.sleep(0.6)  # the late year finishes and is cached
    monkeypatch.setattr(urban, "finance", real)
    later = await s.get_financial_snapshot("999001", years=3)
    assert [row[0] for row in later["data"]["history"]["rows"]] == [2021, 2022, 2023]


async def test_first_call_for_the_national_directory_answers_inside_the_deadline_and_finishes_later(upstream, monkeypatch):
    monkeypatch.setattr(bounded, "DEADLINE", 0.1)
    real = urban.directory

    async def slow(guard, year):
        await asyncio.sleep(0.4)
        return await real(guard, year)

    monkeypatch.setattr(urban, "directory", slow)
    with pytest.raises(ToolError, match="downloaded for the first time"):
        await s.resolve_institution("Test Community College A")
    await asyncio.sleep(0.6)
    monkeypatch.setattr(bounded, "DEADLINE", 45.0)
    r = await s.resolve_institution("Test Community College A")
    assert r["data"]["candidates"][0]["unitid"] == "999001"


async def test_enrollment_trend_on_an_empty_cache_asks_for_one_institution_not_every_institution(upstream):
    r = await s.get_enrollment_trend("999001")
    assert len(r["data"]["rows"]) == 10
    enr = [q for q in upstream.requests if "/fall-enrollment/" in q.url.path]
    assert enr and all(q.url.params.get("unitid") in ("999001", urban.PROBE_UNITID) for q in enr)  # no whole-year table was downloaded


async def test_enrollment_trend_uses_a_cached_whole_year_table_when_there_is_one(upstream):
    await s.compare_peers("999001")  # downloads and caches the whole-year tables
    before = len([q for q in upstream.requests if "/fall-enrollment/" in q.url.path])
    r = await s.get_enrollment_trend("999001")
    assert len(r["data"]["rows"]) == 10
    assert len([q for q in upstream.requests if "/fall-enrollment/" in q.url.path]) == before


async def test_timeouts_small_queries_are_short_and_bulk_downloads_are_longer(upstream):
    assert http.DEFAULT_TIMEOUT < http.BULK_TIMEOUT
    assert s.guard()._client.timeout.read == http.DEFAULT_TIMEOUT
    seen = []
    g = s.guard()
    orig = g._fetch

    async def spy(url, headers, host, max_bytes, attempts, timeout=None):
        seen.append(timeout)
        return await orig(url, headers, host, max_bytes, attempts, timeout)

    g._fetch = spy
    await urban.directory(g, 2024)
    assert seen and all(t == http.BULK_TIMEOUT for t in seen)


async def test_the_year_probes_and_the_download_share_one_deadline(upstream, monkeypatch):
    """Found live: the download was bounded but the probes before it were not, so a slow first call took 79 s."""
    monkeypatch.setattr(bounded, "DEADLINE", 0.15)
    real = urban.latest_year

    async def slow(g):
        await asyncio.sleep(0.4)
        return await real(g)

    monkeypatch.setattr(urban, "latest_year", slow)
    with pytest.raises(ToolError, match="downloaded for the first time"):
        await s.resolve_institution("Test Community College A")
    await asyncio.sleep(0.8)
    monkeypatch.setattr(bounded, "DEADLINE", 45.0)
    monkeypatch.setattr(urban, "latest_year", real)
    assert (await s.resolve_institution("Test Community College A"))["data"]["candidates"][0]["unitid"] == "999001"


async def test_the_directory_request_asks_only_for_the_fields_it_keeps(upstream):
    await s.resolve_institution("Test Community College A")
    q = next(r for r in upstream.requests if "/directory/" in r.url.path and "fields" in r.url.params)
    assert set(q.url.params["fields"].split(",")) == set(urban.DIRECTORY_FIELDS) and "cbsa" in q.url.params["fields"]
