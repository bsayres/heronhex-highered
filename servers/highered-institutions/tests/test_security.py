import httpx
import pytest

from highered_institutions import cache, server
from highered_institutions.http import Guard, UpstreamError
from highered_institutions.models import envelope  # noqa: F401


async def rejected(name, args) -> bool:
    """True if the call fails (raised or isError) instead of returning data."""
    try:
        res = await server.mcp.call_tool(name, args)
    except Exception:  # noqa: BLE001
        return True
    return bool(getattr(res, "is_error", False))


@pytest.mark.parametrize("name,args", [
    ("get_enrollment_trend", {"unitid": "12ab56"}),
    ("get_enrollment_trend", {"unitid": "1234567"}),
    ("get_enrollment_trend", {"unitid": "123456; DROP"}),
    ("get_enrollment_trend", {"unitid": "１６７６３１"}),  # full-width digits must not satisfy a digit pattern
    ("get_financial_snapshot", {"unitid": "１６７６３１"}),
    ("get_institution_profile", {"unitid": "../../etc"}),
    ("resolve_institution", {"query": "x" * 5000}),
    ("resolve_institution", {"query": "ok name", "kind": "sql"}),
    ("resolve_institution", {"query": "Test College A", "state": "Massachusetts"}),
    ("search_institutions", {"limit": 100000}),
    ("search_institutions", {"control": "nonprofit"}),
    ("search_institutions", {"name_contains": "<script>alert(1)</script>"}),
    ("compare_peers", {"unitid": "999001", "n_peers": 500}),
    ("get_enrollment_trend", {"unitid": "999001", "start_year": 1500}),
])
async def test_bad_input_is_rejected(upstream, name, args):
    assert await rejected(name, args)
    assert not upstream.requests  # rejected before any network use


async def test_wrong_explicit_kind_is_rejected(upstream):
    assert await rejected("resolve_institution", {"query": "Test College A", "kind": "unitid"})


async def test_disallowed_host_blocked():
    g = Guard(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    with pytest.raises(UpstreamError, match="allowlist"):
        await g.get_json("https://evil.example.com/x")
    with pytest.raises(UpstreamError, match="https"):
        await g.get_json("http://educationdata.urban.org/x")
    with pytest.raises(UpstreamError):
        await g.get_json("https://user:pw@educationdata.urban.org/x")


async def test_redirect_to_other_host_blocked():
    seen = []

    def handler(req):
        seen.append(req.url.host)
        return httpx.Response(302, headers={"location": "https://evil.example.com/steal"})

    g = Guard(transport=httpx.MockTransport(handler), min_interval={})
    with pytest.raises(UpstreamError, match="allowlist"):
        await g.get_json("https://educationdata.urban.org/api/v1/x")
    assert seen == ["educationdata.urban.org"]  # never contacted the other host


async def test_redirect_to_http_blocked():
    g = Guard(transport=httpx.MockTransport(lambda r: httpx.Response(301, headers={"location": "http://educationdata.urban.org/x"})), min_interval={})
    with pytest.raises(UpstreamError, match="https"):
        await g.get_json("https://educationdata.urban.org/x")


async def test_response_size_limit():
    g = Guard(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"[" + b"1," * 10_000 + b"1]")), min_interval={})
    with pytest.raises(UpstreamError, match="size limit"):
        await g.get_json("https://educationdata.urban.org/x", max_bytes=1000)


async def test_retries_are_bounded_and_errors_do_not_leak():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503)

    g = Guard(transport=httpx.MockTransport(handler), backoff=0, min_interval={})
    with pytest.raises(UpstreamError) as e:
        await g.get_json("https://api.data.gov/ed/collegescorecard/v1/schools", params={"id": "1"}, headers={"X-Api-Key": "SECRETKEY"})
    assert len(calls) == 3
    assert "SECRETKEY" not in str(e.value) and "?id=" not in str(e.value) and "/Users" not in str(e.value)


@pytest.mark.parametrize("bad", ["../x.json", "..%2Fx.json", "/etc/passwd", "a/b.json", "x.json/../../y.json", "UPPER.json", "x.txt", "", "a" * 200 + ".json"])
def test_cache_path_traversal_rejected(tmp_path, monkeypatch, bad):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    with pytest.raises(ValueError):
        cache.safe_path(bad)
    with pytest.raises(ValueError):
        cache.write(bad, {}, "x", "y")


def test_cache_rejects_symlink_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path / "c"))
    root = cache.cache_dir()
    root.mkdir(parents=True)
    (tmp_path / "outside.json").write_text("{}")
    (root / "link.json").symlink_to(tmp_path / "outside.json")
    with pytest.raises(ValueError):
        cache.safe_path("link.json")


def test_cache_checksum_detects_tampering(tmp_path, monkeypatch):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    cache.write("a.json", {"k": 1}, "asof", "https://x")
    assert cache.read("a.json")["data"] == {"k": 1}
    p = cache.safe_path("a.json")
    p.write_text(p.read_text().replace('"k":1', '"k":2'))
    assert cache.read("a.json") is None


async def test_stale_cache_served_when_refresh_fails(upstream, tmp_path):
    await server.resolve_institution("999001")
    # age the directory cache beyond the TTL and break the upstream
    import json
    p = cache.safe_path("urban-directory-2025.json")
    blob = json.loads(p.read_text())
    blob["meta"]["retrieved_at"] = "2020-01-01T00:00:00+00:00"
    p.write_text(json.dumps(blob))
    server.set_guard(Guard(transport=httpx.MockTransport(lambda r: httpx.Response(503)), backoff=0, min_interval={}))
    r = await server.resolve_institution("999001")
    assert r["sources"][0]["served_stale_cache"] is True and r["warnings"]


def test_tools_are_read_only_and_descriptions_static():
    import asyncio
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == {"resolve_institution", "search_institutions", "get_institution_profile", "get_enrollment_trend", "compare_peers", "get_financial_snapshot"}
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)
