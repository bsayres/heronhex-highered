import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_labor_market import cache, server
from highered_labor_market.sources import projections

from .conftest import CONTACT, pc_row


def pc_requests(up):
    return [q for q in up.requests if q.url.host == "public.projectionscentral.org"]


def test_row_validation_rejects_malformed_rows_and_unsafe_urls():
    good = pc_row("25", "Massachusetts", "29-1141", "Registered Nurses", 100, 110, 10)
    assert projections.row(good)["annual_openings"] == 10 and projections.row(good)["fips"] == "25"
    for bad in ({**good, "OccCode": "../x"}, {**good, "OccCode": "29-1141\n"}, {**good, "STFIPS": "ab"}, {**good, "BaseYear": "24"}, {**good, "ProjYear": "x"}, "text", None):
        assert projections.row(bad) is None
    assert projections.row({**good, "StateURL": "http://insecure.example.org/x"})["agency_url"] is None
    assert projections.row({**good, "StateURL": "https://ok.example.org/a b"})["agency_url"] is None
    assert projections.row({**good, "Base": "n/a"})["base"] is None  # unparseable numbers become null, not zero


def test_request_codes_add_broad_groups_once():
    assert projections.request_codes(["31-1121", "31-1122", "29-1141"]) == ["31-1121", "31-1120", "31-1122", "29-1141", "29-1140"]


async def test_state_outlook_with_us_row_one_request_and_disclaimer(upstream):
    r = await server.get_state_occupation_outlook("MA", "29-1141")
    d = r["data"]
    assert d["state_outlook"]["annual_openings"] == 4930 and d["state_outlook"]["base_year"] == 2024 and d["state_outlook"]["projection_year"] == 2034
    assert d["united_states_same_source"]["annual_openings"] == 189100 and d["state_outlook"]["agency_url"].startswith("https://www.mass.gov/")
    assert d["state_match"] == "exact" and "agency_url" in d["regional_projections"]
    assert any("responsibility of each agency" in w for w in r["warnings"]) and any("not BLS national 2025-35" in w for w in r["warnings"])
    reqs = pc_requests(upstream)
    assert len(reqs) == 1 and reqs[0].url.path == "/Projections/LongTermRestJson/25+0/29-1141+29-1140" and reqs[0].url.params["items_per_page"] == "1000"
    for k in ("source", "source_url", "as_of", "retrieved_at"):
        assert r[k]
    assert "untrusted" in r["notice"]


async def test_contact_email_is_not_sent_to_projections_central(upstream):
    await server.get_state_occupation_outlook("MA", "29-1141")
    await server.get_occupation_outlook("29-1141")  # BLS does get it
    assert all(CONTACT not in q.headers["user-agent"] for q in pc_requests(upstream))
    assert any(CONTACT in q.headers["user-agent"] for q in upstream.requests if q.url.host == "www.bls.gov")


async def test_second_call_and_other_states_use_the_cache(upstream):
    await server.get_state_occupation_outlook("MA", "29-1141")
    await server.get_state_occupation_outlook("MA", "29-1141")
    assert len(pc_requests(upstream)) == 1
    r = await server.get_state_occupation_outlook("AL", "29-1141")  # the US row is cached; only Alabama is new, so one request
    assert r["data"]["state_outlook"]["annual_openings"] == 3270 and len(pc_requests(upstream)) == 2
    assert pc_requests(upstream)[1].url.path.split("/")[3] == "1+0"


async def test_expired_entries_are_refetched_and_corrupt_cache_is_ignored(upstream):
    await server.get_state_occupation_outlook("MA", "29-1141")
    assert len(pc_requests(upstream)) == 1
    for name in ("pc-long-25.json", "pc-long-0.json"):  # rewrite with a valid checksum but old fetch times
        data = json.loads(cache.safe_path(name).read_text())["data"]
        for e in data.values():
            e["fetched"] = "2020-01-01T00:00:00+00:00"
        cache.write(name, data, "x", "https://x")
    upstream.pc["LongTermRestJson"][1] = pc_row("25", "Massachusetts", "29-1141", "Registered Nurses", 91850, 95000, 5000)
    r = await server.get_state_occupation_outlook("MA", "29-1141")
    assert len(pc_requests(upstream)) == 2 and r["data"]["state_outlook"]["annual_openings"] == 5000  # fresh data replaced the expired entry
    p = cache.safe_path("pc-long-25.json")  # tamper: the checksum no longer matches, so the file is ignored and refetched
    p.write_text(p.read_text().replace("5000", "7777"))
    r = await server.get_state_occupation_outlook("MA", "29-1141")
    assert len(pc_requests(upstream)) == 3 and r["data"]["state_outlook"]["annual_openings"] == 5000


async def test_broad_group_fallback_is_flagged(upstream):
    r = await server.get_state_occupation_outlook("MA", "31-1121")
    assert r["data"]["state_match"] == "broad_group" and r["data"]["state_outlook"]["occupation"] == "Home Health and Personal Care Aides"
    assert any("broad group 31-1120" in w for w in r["warnings"])


async def test_missing_state_and_unknown_occupation_are_nulls_with_reasons(upstream):
    r = await server.get_state_occupation_outlook("AL", "29-1141", horizon="short")
    assert r["data"]["state_outlook"] is None and r["data"]["united_states_same_source"] is None
    assert {n["field"] for n in r["nulls"]} == {"state_outlook", "united_states_same_source"} and "far fewer states" in r["nulls"][0]["reason"]
    r = await server.get_state_occupation_outlook("MA", "99-9999")  # upstream answers 404 'No results found.'
    assert r["data"]["state_outlook"] is None and r["nulls"][0]["field"] == "state_outlook"
    r = await server.get_state_occupation_outlook("MA", "29-1141", horizon="short")
    assert r["data"]["state_outlook"]["projection_year"] == 2027 and r["data"]["united_states_same_source"] is None


async def test_different_periods_between_state_and_us_are_warned(upstream):
    upstream.pc["LongTermRestJson"][0] = pc_row("0", " United States", "29-1141", "Registered Nurses", 3300000, 3500000, 189100, years=("2025", "2035"))
    r = await server.get_state_occupation_outlook("MA", "29-1141")
    assert any("different years" in w for w in r["warnings"])


async def test_rows_that_were_not_asked_for_are_dropped_not_shown(upstream):
    upstream.pc_extra = [pc_row("48", "Texas", "29-1141", "Registered Nurses", 1, 2, 3), pc_row("25", "Massachusetts", "11-1011", "Chief Executives", 1, 2, 3),
                         pc_row("25", "Massachusetts", "29-1141\n", "Injected", 1, 2, 3)]
    r = await server.get_state_occupation_outlook("MA", "29-1141")
    assert "Texas" not in json.dumps(r["data"]) and "Chief Executives" not in json.dumps(r["data"]) and "Injected" not in json.dumps(r["data"])
    assert r["data"]["state_outlook"]["annual_openings"] == 4930
    assert any("3 upstream row(s) were dropped" in w for w in r["warnings"])  # Texas, the unrequested occupation, and the malformed code


async def test_unexpected_shapes_paging_and_errors_fail_safely(upstream):
    upstream.pc_pages = 2
    with pytest.raises(ToolError, match="more pages"):
        await server.get_state_occupation_outlook("MA", "29-1141")
    upstream.pc_pages = 1
    server.set_guard(server.Guard(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"rows": "x", "pager": {}})), backoff=0, min_interval={}, contact=CONTACT))
    with pytest.raises(ToolError, match="unexpected response"):
        await server.get_state_occupation_outlook("MA", "29-1141")
    server.set_guard(server.Guard(transport=httpx.MockTransport(lambda r: httpx.Response(500)), backoff=0, min_interval={}, contact=CONTACT))
    with pytest.raises(ToolError) as e:
        await server.get_state_occupation_outlook("MA", "29-1141")
    assert "http" not in str(e.value) and CONTACT not in str(e.value)


async def test_stale_cache_is_served_when_a_refresh_fails(upstream):
    await server.get_state_occupation_outlook("MA", "29-1141")
    p = cache.safe_path("pc-long-25.json")
    blob = json.loads(p.read_text())
    for e in blob["data"].values():
        e["fetched"] = "2020-01-01T00:00:00+00:00"
    cache.write("pc-long-25.json", blob["data"], "x", "https://x")  # valid checksum, expired entries
    upstream.pc_status = 503
    r = await server.get_state_occupation_outlook("MA", "29-1141")
    assert r["sources"][0]["served_stale_cache"] is True and r["data"]["state_outlook"]["annual_openings"] == 4930 and any("refresh failed" in w for w in r["warnings"])


async def test_alignment_with_state_adds_state_demand_beside_national(upstream):
    r = await server.get_program_alignment("999001", "51.38", 2, state="MA")
    sd = r["data"]["state_demand"]
    rows = {x[0]: x for x in sd["rows"]}
    assert rows["29-1141"][3] == 4930 and rows["29-1141"][6] == 189100 and rows["29-1141"][7] == "2024-2034" and rows["25-1072"][3] == 280
    s = sd["summary"]
    assert s["state_annual_openings_all_mapped"] == 5210 and s["united_states_same_source_annual_openings_all_mapped"] == 197700 and s["period"] == "2024-2034"
    assert s["state_annual_openings_education_matched"] == 0 and sd["regional_projections"].startswith("Not available")
    assert r["data"]["openings_summary"]["annual_openings_all_mapped"] == 189300  # BLS national 2025-35 stays separate
    assert any("different period from BLS national" in w for w in r["warnings"]) and any("not the institution's region" in w for w in r["warnings"])
    assert any(s_["source"].startswith("Projections Central") for s_ in r["sources"])


async def test_alignment_without_state_has_no_state_block_and_state_works_without_bls_contact(upstream, monkeypatch):
    r = await server.get_program_alignment("999001", "51.38", 2)
    assert r["data"]["state_demand"] is None and not pc_requests(upstream)
    monkeypatch.delenv("HIGHERED_MCPS_CONTACT")
    cache.safe_path("bls-projections.json").unlink()
    r = await server.get_program_alignment("999001", "51.38", 2, state="MA")
    assert r["data"]["state_demand"]["summary"]["state_annual_openings_all_mapped"] == 5210
    assert r["data"]["state_demand"]["summary"]["state_annual_openings_education_matched"] is None  # needs BLS's education classification
    assert any(n["field"] == "bls_projections" for n in r["nulls"])


async def test_alignment_counts_a_broad_state_group_once_and_batches_requests(upstream, monkeypatch):
    monkeypatch.setattr(projections, "BATCH", 2)
    r = await server.get_program_alignment("999001", "51.39", 1, state="MA")
    s = r["data"]["state_demand"]["summary"]
    assert s["occupations_mapped"] == 2 and s["distinct_state_rows_counted"] == 1 and s["state_annual_openings_all_mapped"] == 18800
    reqs = pc_requests(upstream)
    assert [len(q.url.path.split("/")[-1].split("+")) for q in reqs] == [2, 1]  # 3 distinct codes (two detailed, one shared broad group) in batches of 2
    assert any("no state projection" in w for w in r["warnings"])


@pytest.mark.parametrize("name,args", [
    ("get_state_occupation_outlook", {"state": "XX", "soc": "29-1141"}), ("get_state_occupation_outlook", {"state": "ma", "soc": "29-1141"}),
    ("get_state_occupation_outlook", {"state": "Massachusetts", "soc": "29-1141"}), ("get_state_occupation_outlook", {"state": "MA", "soc": "29-114"}),
    ("get_state_occupation_outlook", {"state": "MA", "soc": "29-1141+11-1011"}), ("get_state_occupation_outlook", {"state": "MA", "soc": "29-1141/all"}),
    ("get_state_occupation_outlook", {"state": "MA", "soc": "２９-1141"}), ("get_state_occupation_outlook", {"state": "MA", "soc": "29-1141\n"}),
    ("get_state_occupation_outlook", {"state": "MA", "soc": "29-1141", "horizon": "medium"}), ("get_state_occupation_outlook", {"state": "25+0", "soc": "29-1141"}),
    ("get_program_alignment", {"unitid": "999001", "cip4": "51.38", "credential": 2, "state": "25"}),
    ("get_program_alignment", {"unitid": "999001", "cip4": "51.38", "credential": 2, "state": "MA", "horizon": "x"}),
])
async def test_bad_projection_inputs_rejected_before_network(upstream, name, args):
    try:
        res = await server.mcp.call_tool(name, args)
        failed = bool(getattr(res, "is_error", False))
    except Exception:  # noqa: BLE001
        failed = True
    assert failed and not upstream.requests
