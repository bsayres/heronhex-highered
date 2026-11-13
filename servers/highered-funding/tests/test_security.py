import httpx
import pytest

from highered_funding import cache, server
from highered_funding.http import Guard, UpstreamError


async def test_disallowed_host_blocked_for_get_and_post():
    g = Guard(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})), min_interval={})
    with pytest.raises(UpstreamError, match="allowlist"):
        await g.get_json("https://evil.example.com/x")
    with pytest.raises(UpstreamError, match="allowlist"):
        await g.post_json("https://evil.example.com/x", {})
    with pytest.raises(UpstreamError, match="only https"):
        await g.get_json("http://api.nsf.gov/services/v1/awards.json")


async def test_post_only_to_the_two_search_apis():
    seen = []
    g = Guard(transport=httpx.MockTransport(lambda r: seen.append(r.url.host) or httpx.Response(200, json={})), min_interval={})
    for host in ("api.nsf.gov", "ncses.nsf.gov", "shef.sheeo.org", "www.wiche.edu"):
        with pytest.raises(UpstreamError, match="POST is not allowed"):
            await g.post_json(f"https://{host}/x", {})
    assert seen == []  # blocked before any request left the process
    await g.post_json("https://api.grants.gov/v1/api/search2", {})
    assert seen == ["api.grants.gov"]


async def test_redirects_are_checked_per_hop_and_never_followed_on_post():
    seen = []

    def handler(req):
        seen.append(req.url.host)
        return httpx.Response(302, headers={"location": "https://evil.example.com/x"})

    g = Guard(transport=httpx.MockTransport(handler), min_interval={})
    with pytest.raises(UpstreamError, match="allowlist"):
        await g.get_bytes("https://ncses.nsf.gov/file.zip")
    with pytest.raises(UpstreamError, match="redirected a POST"):
        await g.post_json("https://api.reporter.nih.gov/v2/projects/search", {})
    assert set(seen) == {"ncses.nsf.gov", "api.reporter.nih.gov"}


async def test_response_size_cap_and_error_messages_leak_nothing():
    g = Guard(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"0" * 10_000)), min_interval={})
    with pytest.raises(UpstreamError, match="size limit"):
        await g.get_bytes("https://shef.sheeo.org/x", max_bytes=1_000)
    with pytest.raises(UpstreamError, match="size limit"):
        await g.post_json("https://api.grants.gov/x", {}, max_bytes=1_000)
    g = Guard(transport=httpx.MockTransport(lambda r: httpx.Response(500)), backoff=0, min_interval={})
    with pytest.raises(UpstreamError) as e:
        await g.post_json("https://api.reporter.nih.gov/v2/projects/search", {"criteria": {"org_names": ["SECRETNAME"]}})
    assert "SECRETNAME" not in str(e.value) and "http" not in str(e.value)


@pytest.mark.parametrize("bad", ["../x.json", "/etc/passwd", "a/b.json", "x.json/../../y.json", "X.json", ""])
def test_cache_traversal_rejected(tmp_path, monkeypatch, bad):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    with pytest.raises(ValueError):
        cache.safe_path(bad)


def test_query_text_allows_accented_names_but_no_line_breaks_or_other_scripts_digits():
    from pydantic import TypeAdapter, ValidationError

    from highered_funding.models import QueryText

    text = TypeAdapter(QueryText)
    assert text.validate_python("Universidad Ana G. Méndez") == "Universidad Ana G. Méndez"
    for bad in ("Col١ege", "community\ncollege", "a\tb", "９９９"):
        with pytest.raises(ValidationError):
            text.validate_python(bad)


def test_cache_tamper_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    cache.write("a.json", {"k": 1}, "x", "https://x")
    p = cache.safe_path("a.json")
    p.write_text(p.read_text().replace('"k":1', '"k":2'))
    assert cache.read("a.json") is None


async def test_tools_are_read_only_with_static_descriptions():
    tools = await server.mcp.list_tools()
    assert {t.name for t in tools} == {"get_research_spend", "search_grant_awards", "search_funding_opportunities", "get_state_funding", "get_enrollment_projection"}
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)
