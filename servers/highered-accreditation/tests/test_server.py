import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_accreditation import cache, http, server
from highered_accreditation.http import Guard, UpstreamError

from .conftest import INJECTION, PII, make_zip


async def rejected(name, args):
    try:
        res = await server.mcp.call_tool(name, args)
        return bool(getattr(res, "is_error", False))
    except Exception:  # noqa: BLE001
        return True


async def test_status_for_college_a(upstream):
    r = await server.get_accreditation_status("999001")
    d = r["data"]
    assert (d["dapip_id"], d["opeid"], d["name_in_dapip"]) == ("990001", "09990100", "Test Community College A")
    assert r["as_of"] == "actions recorded through 2026-10-29" and r["source_url"] == "https://ope.ed.gov/dapip/" and r["retrieved_at"]
    by_scope = {(x["scope"], x["current"]) for x in d["accreditors"]}
    assert by_scope == {("institutional", True), ("programmatic", False)}
    s = d["summary"]
    assert s["current_institutional_accreditors"] == ["New England Commission of Higher Education"]
    assert s["current_programs"] == [] and s["not_current"] == 2
    ended = {p["program"].split(" ")[0]: p for p in s["not_current_programs"]}
    assert ended["Nursing"]["end_date"] == "2019-12-31" and ended["Nursing"]["last_action"]["category"] == "loss"
    assert ended["Nursing"]["last_action"]["action"].startswith("Loss of Accreditation") and ended["Nursing"]["last_action"]["date"] == "2019-12-31"
    assert ended["Radiologic"]["last_action"] == {"date": "2022-08-23", "action": "Loss of Accreditation or Preaccreditation: Other", "category": "loss"}
    assert any("end date that has passed" in w for w in r["warnings"])
    assert d["coverage"]["state_agencies_in_dapip"] and "authority" in d["coverage"]["verify_with"]
    assert r["notice"]


async def test_last_action_is_the_newest_action_on_that_record_or_null(upstream):
    recs = {(r["agency_name"], r["program"]): r for r in (await server.get_accreditation_status("999001"))["data"]["accreditors"]}
    neche = next(r for (a, p), r in recs.items() if p == "Institutional Accreditation")
    assert neche["last_action"] == {"date": "2025-09-25", "action": "Renewal of Accreditation", "category": "routine"}  # newest of three
    # An ended record with no recorded action must say so (null), not borrow another record's action.
    none = next(r for r in (await server.get_accreditation_status("111111"))["data"]["accreditors"] if r["agency_name"] == "Some Specialty Council")
    assert none["last_action"] is None and not none["current"]
    summary = (await server.get_accreditation_status("111111", scope="programmatic"))["data"]["summary"]["not_current_programs"]
    assert summary == [{"program": "Business (BUS)", "agency_name": "Some Specialty Council", "end_date": None, "status_as_recorded": "Denied Accreditation", "last_action": None}]


async def test_sources_carry_checksum_and_download_endpoint(upstream):
    r = await server.get_accreditation_status("999001")
    s = r["sources"][0]
    assert len(s["file_sha256"]) == 64 and s["served_stale_cache"] is False and s["download_endpoint"] == http.DOWNLOAD_URL


async def test_scope_filters(upstream):
    inst = (await server.get_accreditation_status("999001", scope="institutional"))["data"]
    assert [x["agency_name"] for x in inst["accreditors"]] == ["New England Commission of Higher Education"]
    prog = (await server.get_accreditation_status("999001", scope="programmatic"))["data"]
    assert all(x["scope"] == "programmatic" for x in prog["accreditors"]) and len(prog["accreditors"]) == 2
    r = await server.get_accreditation_status("999001", scope="state")
    assert r["data"]["accreditors"] == [] and r["nulls"][0]["field"] == "accreditors"
    st = (await server.get_accreditation_status("300000", scope="state"))["data"]
    assert [x["agency_type"] for x in st["accreditors"]] == ["state_agency"]


@pytest.mark.parametrize("unitid", ["123456", "999999", "100999", "990001"])
async def test_unknown_unitid_is_a_null_with_a_reason(upstream, unitid):
    for call in (server.get_accreditation_status, server.get_accreditation_actions):
        r = await call(unitid)
        assert r["nulls"][0]["field"] == "institution" and "does not show" in r["nulls"][0]["reason"]
        assert not r["data"].get("accreditors") and not r["data"].get("actions")


async def test_institution_with_two_unitids_resolves_from_either(upstream):
    a = await server.get_accreditation_status("111111")
    b = await server.get_accreditation_status("222222")
    assert a["data"]["dapip_id"] == b["data"]["dapip_id"] == "100500"


async def test_actions_newest_first_with_counts(upstream):
    r = await server.get_accreditation_actions("999001")
    d = r["data"]
    dates = [a["date"] for a in d["actions"]]
    assert dates == sorted(dates, reverse=True) and dates[0] == "2025-09-25" and dates[-1] == "2015-09-25"
    assert d["matched"] == d["returned"] == 8
    assert d["counts_by_category"] == {"routine": 2, "monitoring": 1, "adverse": 2, "substantive_change": 1, "loss": 2}
    assert set(d["category_notes"]) == set(d["counts_by_category"])
    first = next(a for a in d["actions"] if a["action"] == "Heightened Monitoring or Focused Review")
    assert first["category"] == "monitoring" and "Educational Effectiveness" in first["justification_detail"]
    assert first["justification"].startswith("Other")
    assert not r["warnings"]


async def test_actions_filters_and_limit(upstream):
    d = (await server.get_accreditation_actions("999001", since_year=2022))["data"]
    assert [a["date"] for a in d["actions"]] == ["2025-09-25", "2023-03-03", "2022-08-23", "2022-01-18"]
    prog = (await server.get_accreditation_actions("999001", scope="programmatic"))["data"]
    assert {a["scope"] for a in prog["actions"]} == {"programmatic"} and prog["matched"] == 5
    r = await server.get_accreditation_actions("999001", limit=3)
    assert r["data"]["matched"] == 8 and r["data"]["returned"] == 3 and len(r["data"]["actions"]) == 3
    assert sum(r["data"]["counts_by_category"].values()) == 8  # counts cover everything that matched, not just the page
    assert any("showing the newest 3" in w for w in r["warnings"])
    empty = await server.get_accreditation_actions("999001", since_year=2030)
    assert empty["nulls"][0]["field"] == "actions" and "since 2030" in empty["nulls"][0]["reason"]


async def test_unknown_wording_and_bad_dates_are_reported_not_guessed(upstream):
    d = (await server.get_accreditation_actions("300000"))["data"]
    unknown = next(a for a in d["actions"] if a["action"] == "Brand New Action Wording")
    assert unknown["category"] == "unclassified"
    undated = next(a for a in d["actions"] if a["date"] is None)
    assert undated is d["actions"][-1]  # undated rows sort last
    assert d["counts_by_category"]["unclassified"] == 1
    assert d["actions"][1]["category"] == "loss"  # Removal of Approval of a Program, by a state agency
    state = (await server.get_accreditation_actions("300000", scope="state"))["data"]
    assert [a["agency_type"] for a in state["actions"]] == ["state_agency"]


async def test_upstream_text_is_returned_as_data_and_bounded(upstream):
    r = await server.get_accreditation_actions("300000")
    detail = next(a for a in r["data"]["actions"] if a["action"] == "Brand New Action Wording")["justification_detail"]
    assert INJECTION in detail and len(detail) <= 400 and "\x00" not in detail
    assert "untrusted" in r["notice"]
    name = (await server.get_accreditation_status("300000"))["data"]["name_in_dapip"]
    assert INJECTION in name and "\x1b" not in name


async def test_no_personal_data_in_responses_or_cache(upstream, tmp_path):
    blob = json.dumps([await server.get_accreditation_status(u) for u in ("999001", "111111", "300000")]
                      + [await server.get_accreditation_actions(u) for u in ("999001", "111111", "300000")])
    cached = (tmp_path / "cache" / "accreditation" / "dapip.json").read_text()
    for s in PII:
        assert s not in blob and s not in cached


async def test_only_the_fixed_post_is_ever_sent(upstream):
    await server.get_accreditation_status("999001")
    assert len(upstream.requests) == 1
    req = upstream.requests[0]
    assert (req.method, str(req.url)) == ("POST", http.DOWNLOAD_URL)
    assert json.loads(req.content) == http.DOWNLOAD_BODY


# ---- cache: 30-day refresh, stale fallback, corruption ----------------------------------------------

async def test_fresh_cache_makes_no_request(upstream):
    await server.get_accreditation_status("999001")
    await server.get_accreditation_actions("999001")
    await server.get_accreditation_status("111111")
    assert len(upstream.requests) == 1


def _age_cache(tmp_path, days):
    path = tmp_path / "cache" / "accreditation" / "dapip.json"
    blob = json.loads(path.read_text())
    blob["meta"]["retrieved_at"] = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")
    path.write_text(json.dumps(blob))


async def test_cache_refreshes_after_30_days_and_not_before(upstream, tmp_path):
    await server.get_accreditation_status("999001")
    _age_cache(tmp_path, 29)
    await server.get_accreditation_status("999001")
    assert len(upstream.requests) == 1
    _age_cache(tmp_path, 31)
    await server.get_accreditation_status("999001")
    assert len(upstream.requests) == 2


async def test_failed_refresh_serves_stale_cache_with_a_warning(upstream, tmp_path):
    await server.get_accreditation_status("999001")
    _age_cache(tmp_path, 60)
    upstream.status = 503
    r = await server.get_accreditation_status("999001")
    assert r["sources"][0]["served_stale_cache"] is True and any("30-day" in w for w in r["warnings"])
    assert r["data"]["accreditors"]


async def test_no_cache_and_upstream_down_is_a_clean_error(upstream):
    upstream.status = 503
    with pytest.raises(ToolError) as e:
        await server.get_accreditation_status("999001")
    assert "ope.ed.gov" in str(e.value) and "/dapip/" not in str(e.value) and "Users" not in str(e.value)


async def test_corrupt_cache_is_refetched(upstream, tmp_path):
    await server.get_accreditation_status("999001")
    path = tmp_path / "cache" / "accreditation" / "dapip.json"
    blob = json.loads(path.read_text())
    blob["data"]["institutions"]["999001"]["name"] = "Tampered"
    path.write_text(json.dumps(blob))
    r = await server.get_accreditation_status("999001")
    assert r["data"]["name_in_dapip"] == "Test Community College A" and len(upstream.requests) == 2


async def test_garbage_download_is_rejected_and_not_cached(upstream, tmp_path):
    upstream.body = b"<html>Access denied</html>"
    with pytest.raises(ToolError):
        await server.get_accreditation_status("999001")
    assert not (tmp_path / "cache" / "accreditation" / "dapip.json").exists()


@pytest.mark.parametrize("name", ["../x.json", "x.json\n", "X.json", "a/b.json", "x.json.tmp", "", ".json", "x" * 90 + ".json", "..%2fx.json", "a..b.json", "..", "...json"])
def test_cache_names_cannot_escape(name):
    with pytest.raises(ValueError):
        cache.safe_path(name)


# ---- network guard ---------------------------------------------------------------------------------

async def test_redirect_on_post_is_not_followed(upstream):
    upstream.redirect_to = "https://evil.example/dapip.zip"
    with pytest.raises(ToolError, match="redirected"):
        await server.get_accreditation_status("999001")
    assert all(r.url.host == "ope.ed.gov" for r in upstream.requests)


async def test_post_is_limited_to_the_one_download_url():
    g = Guard(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x")), backoff=0)
    for url in ("https://ope.ed.gov/dapip/api/other", "https://ope.ed.gov/dapip/", "https://evil.example/dapip/api/downloadFiles/accreditationDataFiles",
                "http://ope.ed.gov/dapip/api/downloadFiles/accreditationDataFiles", "https://ope.ed.gov:8443/dapip/api/downloadFiles/accreditationDataFiles",
                "https://user:pw@ope.ed.gov/dapip/api/downloadFiles/accreditationDataFiles", "https://ope.ed.gov.evil.example/x"):
        with pytest.raises(UpstreamError, match="Blocked"):
            await g.post_download(url)


async def test_response_size_cap():
    g = Guard(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 5000)), backoff=0)
    with pytest.raises(UpstreamError, match="size limit"):
        await g.post_download(max_bytes=1000)


async def test_retries_are_bounded():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503)

    g = Guard(transport=httpx.MockTransport(handler), backoff=0)
    with pytest.raises(UpstreamError):
        await g.post_download(attempts=50)
    assert len(calls) <= http.MAX_ATTEMPTS


async def test_transport_errors_do_not_leak_details():
    def handler(req):
        raise httpx.ConnectError("boom /Users/someone/secret")

    g = Guard(transport=httpx.MockTransport(handler), backoff=0)
    with pytest.raises(UpstreamError) as e:
        await g.post_download()
    assert str(e.value) == "Could not reach ope.ed.gov."


# ---- inputs ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["99900", "9990011", "99900a", "９９９００１", "999001\n", " 999001", "../../etc", "", "999001;DROP", "-99900"])
async def test_bad_unitid_rejected_before_network(upstream, bad):
    for name in ("get_accreditation_status", "get_accreditation_actions"):
        assert await rejected(name, {"unitid": bad})
    assert not upstream.requests


@pytest.mark.parametrize("args", [{"scope": "bogus"}, {"scope": "ALL"}, {"since_year": 1800}, {"since_year": 2101}, {"limit": 0}, {"limit": 201}, {"limit": "5; x"}])
async def test_bad_options_rejected_before_network(upstream, args):
    assert await rejected("get_accreditation_actions", {"unitid": "999001", **args})
    assert not upstream.requests


def test_both_tools_are_marked_read_only():
    import asyncio

    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == {"get_accreditation_status", "get_accreditation_actions"}
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)


def test_zip_fixture_is_valid():
    assert make_zip()[:2] == b"PK"


@pytest.mark.parametrize("url", [
    "http://ope.ed.gov/dapip/", "ftp://ope.ed.gov/dapip/", "file:///etc/passwd", "https://ope.ed.gov:8443/x", "https://user@ope.ed.gov/x",
    "https://evil.example/dapip/", "https://ope.ed.gov.evil.example/", "https://www.ed.gov/", "//ope.ed.gov/dapip/", "",
])
def test_check_url_blocks_everything_but_https_on_the_allowlist(url):
    with pytest.raises(UpstreamError, match="Blocked"):
        http.check_url(url)


def test_check_url_allows_the_dapip_host():
    assert http.check_url(http.DAPIP_PAGE) == "ope.ed.gov"


async def test_both_tools_state_the_window_of_the_action_history(upstream):
    s = await server.get_accreditation_status("999001")
    a = await server.get_accreditation_actions("999001", since_year=2024)  # the window ignores since_year
    for r in (s, a):
        w = r["data"]["action_history"]
        assert w["earliest_action_date"] and w["earliest_action_date"] <= w["latest_action_date"] and w["actions_held"] >= len(a["data"]["actions"])
    assert a["data"]["matched"] < a["data"]["action_history"]["actions_held"]
