import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_labor_market import cache, server
from highered_labor_market.http import NeedsContact, UpstreamError

from .conftest import CONTACT, SC_KEY


async def test_contact_is_sent_to_bls_only_and_never_returned(upstream):
    await server.get_occupation_outlook("29-1141")
    await server.get_occupation_skills("29-1141")
    await server.map_program_to_occupations("51.3801")
    await server.get_program_outcomes("999001")
    by_host = {}
    for q in upstream.requests:
        by_host.setdefault(q.url.host, []).append(q.headers["user-agent"])
    assert all(CONTACT in ua for ua in by_host["www.bls.gov"])
    for host, agents in by_host.items():
        if host != "www.bls.gov":
            assert not any(CONTACT in ua for ua in agents), host
    assert all(CONTACT not in str(q.url) and CONTACT not in (q.content or b"").decode() for q in upstream.requests)
    r = await server.get_occupation_outlook("29-1141")
    assert CONTACT not in json.dumps(r)


@pytest.mark.parametrize("bad", ["", "no-at-sign", "a@b", "x@example.org\r\nX-Evil: 1", "x y@example.org", "@example.org", "a@example.org\n", "a@@example.org", "x" * 70 + "@example.org"])
async def test_invalid_contact_is_refused_before_any_bls_request(upstream, monkeypatch, bad):
    monkeypatch.setenv("HIGHERED_MCPS_CONTACT", bad)
    with pytest.raises(ToolError, match="HIGHERED_MCPS_CONTACT"):
        await server.get_occupation_outlook("29-1141")
    assert not [q for q in upstream.requests if q.url.host == "www.bls.gov"]


async def test_error_text_never_contains_contact_or_urls(upstream):
    upstream.bls_status = 500
    with pytest.raises(ToolError) as e:
        await server.get_occupation_outlook("29-1141")
    assert CONTACT not in str(e.value) and "http" not in str(e.value)


async def test_bls_redirect_to_other_host_is_blocked_and_never_carries_the_contact():
    seen = []

    def handler(req):
        seen.append((req.url.host, req.headers["user-agent"]))
        return httpx.Response(302, headers={"location": "https://evil.example.com/x.xlsx"})

    g = server.Guard(transport=httpx.MockTransport(handler), min_interval={}, contact=CONTACT)
    with pytest.raises(UpstreamError, match="allowlist"):
        await g.get_bytes("https://www.bls.gov/emp/ind-occ-matrix/occupation.xlsx")
    assert [h for h, _ in seen] == ["www.bls.gov"] and CONTACT in seen[0][1]


async def test_redirect_from_another_allowed_host_to_bls_gets_the_contact_only_there():
    seen = []

    def handler(req):
        seen.append((req.url.host, req.headers["user-agent"]))
        if req.url.host == "nces.ed.gov":
            return httpx.Response(302, headers={"location": "https://www.bls.gov/x"})
        return httpx.Response(200, content=b"ok")

    g = server.Guard(transport=httpx.MockTransport(handler), min_interval={}, contact=CONTACT)
    await g.get_bytes("https://nces.ed.gov/x")
    assert CONTACT not in seen[0][1] and CONTACT in seen[1][1]


async def test_disallowed_host_scheme_and_size_cap():
    g = server.Guard(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"0" * 10_000)), min_interval={}, contact=CONTACT)
    with pytest.raises(UpstreamError, match="allowlist"):
        await g.get_json("https://evil.example.com/x")
    with pytest.raises(UpstreamError, match="only https"):
        await g.get_bytes("http://www.bls.gov/x")
    with pytest.raises(UpstreamError, match="size limit"):
        await g.get_bytes("https://www.onetcenter.org/x", max_bytes=1_000)
    with pytest.raises(NeedsContact):
        await server.Guard(transport=httpx.MockTransport(lambda r: httpx.Response(200)), min_interval={}, contact="bad")._bls_agent()


async def test_onet_page_without_version_and_bad_workbooks_fail_safely(upstream):
    upstream.crosswalk = b"PK\x03\x04garbage"
    with pytest.raises(ToolError):
        await server.map_program_to_occupations("51.3801")
    upstream.onet["occupation_data"] = "wrong,header\n1,2\n"
    with pytest.raises(ToolError, match="expected columns"):
        await server.get_occupation_skills("29-1141")


@pytest.mark.parametrize("name,args", [
    ("map_program_to_occupations", {"cip": "51.380"}), ("map_program_to_occupations", {"cip": "513801"}), ("map_program_to_occupations", {"cip": "51.3801 OR 1=1"}),
    ("map_program_to_occupations", {"cip": "５１.３８０１"}), ("map_program_to_occupations", {"cip": "../../etc"}), ("map_program_to_occupations", {"cip": ""}),
    ("get_occupation_outlook", {"soc": "29-114"}), ("get_occupation_outlook", {"soc": "291141"}), ("get_occupation_outlook", {"soc": "29-114１"}),
    ("get_occupation_outlook", {"soc": "29-1141\n"}), ("get_occupation_skills", {"soc": "29-1141", "top": 0}), ("get_occupation_skills", {"soc": "29-1141", "top": 31}),
    ("get_program_outcomes", {"unitid": "16763"}), ("get_program_outcomes", {"unitid": "１６７６３１"}), ("get_program_outcomes", {"unitid": "999001", "credential": 0}),
    ("get_program_outcomes", {"unitid": "999001", "credential": 9}), ("get_program_outcomes", {"unitid": "999001", "cip4": "51.3801"}), ("get_program_outcomes", {"unitid": "999001", "limit": 101}),
    ("get_program_alignment", {"unitid": "999001", "cip4": "51.38"}), ("get_program_alignment", {"unitid": "999001", "cip4": "51.38", "credential": "associate"}),
    ("get_program_alignment", {"unitid": "999001", "cip4": "5138", "credential": 2}), ("get_program_alignment", {"unitid": "999001; DROP", "cip4": "51.38", "credential": 2}),
])
async def test_bad_inputs_rejected_before_network(upstream, name, args):
    try:
        res = await server.mcp.call_tool(name, args)
        failed = bool(getattr(res, "is_error", False))
    except Exception:  # noqa: BLE001
        failed = True
    assert failed and not upstream.requests


@pytest.mark.parametrize("bad", ["../x.json", "/etc/passwd", "a/b.json", "x.json/../../y.json", "X.json", ""])
def test_cache_traversal_rejected(tmp_path, monkeypatch, bad):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    with pytest.raises(ValueError):
        cache.safe_path(bad)


def test_cache_tamper_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    cache.write("a.json", {"k": 1}, "x", "https://x")
    p = cache.safe_path("a.json")
    p.write_text(p.read_text().replace('"k":1', '"k":2'))
    assert cache.read("a.json") is None


async def test_tools_are_read_only_static_and_secret_free(upstream):
    tools = await server.mcp.list_tools()
    assert {t.name for t in tools} == {"get_wages", "search_metros", "find_program_offerings", "search_programs", "map_program_to_occupations", "get_occupation_outlook", "get_state_occupation_outlook", "get_occupation_skills", "get_program_outcomes", "get_program_alignment"}
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)
    blob = json.dumps([t.description for t in tools])
    assert CONTACT not in blob and SC_KEY not in blob and "Ignore previous" not in blob


async def test_upstream_text_is_labeled_untrusted(upstream):
    r = await server.get_occupation_skills("29-1141")
    assert "Ignore previous instructions" in json.dumps(r["data"]) and "untrusted" in r["notice"]


@pytest.mark.parametrize("keyword", ["", "a", "x" * 61, "nursing; DROP TABLE", "nursing\x00", "nursing<script>", "５１"])
async def test_search_programs_rejects_bad_keywords(upstream, keyword):
    with pytest.raises(ToolError):
        await server.mcp.call_tool("search_programs", {"keyword": keyword})


@pytest.mark.parametrize("args", [{"cip4": "51.380", "credential": 2}, {"cip4": "5138", "credential": 2}, {"cip4": "51.38", "credential": 0},
                                  {"cip4": "51.38", "credential": 9}, {"cip4": "51.38", "credential": 2, "state": "ZZ"},
                                  {"cip4": "51.38", "credential": 2, "unitid": "12345"}, {"cip4": "51.38", "credential": 2, "limit": 51},
                                  {"cip4": "51.38&x=1", "credential": 2}])
async def test_find_program_offerings_rejects_bad_input_without_a_request(upstream, args):
    with pytest.raises(ToolError):
        await server.mcp.call_tool("find_program_offerings", args)
    assert not upstream.requests
