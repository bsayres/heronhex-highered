import json

import httpx
import pytest

from highered_risk import cache, server
from highered_risk.http import Guard, UpstreamError
from highered_risk.sources import fsa

from .conftest import CDR_PATH, COMP_PATH, HCM_PATH, composite_xls, zip_bomb_xlsx


def test_discovery_picks_newest_and_rejects_bad_paths():
    page = json.dumps({"x": f'/sites/default/files/Schools-on-HCM-March-2025.xlsx {HCM_PATH} /sites/default/files/Schools-on-hcm-dec-2025.xlsx /sites/default/files/../../etc/Schools-on-hcm-dec-2030.xlsx'})
    assert fsa.pick_hcm(page).endswith("Schools-on-hcm-jun-2026.xlsx")
    assert fsa.pick_composite(f"/sites/default/files/ay16-17-composite-scores.xls {COMP_PATH}").endswith("ay-22-23-composite-scores.xls")
    with pytest.raises(fsa.ParseError):
        fsa.pick_hcm("nothing here")
    with pytest.raises(fsa.ParseError):  # link text present but path escapes the allowed folder
        fsa.pick_cdr('<a href="/../../etc/passwd.xlsx">Official CDRs for the past three fiscal years</a>')
    assert fsa.pick_cdr(f'<a href="{CDR_PATH[:25]}\n{CDR_PATH[25:]}">Official CDRs for the past three fiscal years</a>').endswith("FY2023OfficialFinal.xlsx")


async def test_status_for_listed_scored_and_missing(upstream):
    d = (await server.get_fsa_status("00100200"))["data"]
    assert d["heightened_cash_monitoring"]["listed"] and d["heightened_cash_monitoring"]["as_of"] == "2026-06-01"
    assert d["financial_responsibility"] is None
    assert d["cohort_default_rates"]["entries"][0]["rates"][0]["rate_percent"] == 0.8
    assert [r["opeid"] for r in d["heightened_cash_monitoring"]["other_campuses_same_opeid6_listed"]] == ["00100201"]

    r = await server.get_fsa_status("00884300")
    assert r["data"]["financial_responsibility"]["composite_score"] == 2.2
    assert r["data"]["financial_responsibility"]["fiscal_year_end"] == "2023-05-31"
    assert r["data"]["heightened_cash_monitoring"]["listed"] is False

    r = await server.get_fsa_status("09990100")
    assert {n["field"] for n in r["nulls"]} == {"financial_responsibility", "cohort_default_rates"}
    assert all(n["reason"] for n in r["nulls"])
    for k in ("source", "source_url", "as_of", "retrieved_at"):
        assert r[k]
    assert len(r["sources"]) == 3 and all(s["file_sha256"] for s in r["sources"])


async def test_free_text_is_data_only(upstream):
    r = await server.get_fsa_status("00100200")
    tools = await server.mcp.list_tools()
    assert all("Ignore previous" not in (t.description or "") for t in tools)
    assert "Ignore previous instructions" in json.dumps(r["data"])  # returned as a data field
    assert "untrusted" in r["notice"]


async def test_second_call_uses_cache(upstream):
    await server.get_fsa_status("00100200")
    n = len(upstream.requests)
    await server.get_fsa_status("00884300")
    assert len(upstream.requests) == n


async def test_stale_cache_served_when_refresh_fails(upstream):
    await server.get_fsa_status("00100200")
    for name in ("fsa-hcm.json", "fsa-composite.json", "fsa-cdr.json"):
        p = cache.safe_path(name)
        blob = json.loads(p.read_text())
        blob["meta"]["retrieved_at"] = "2020-01-01T00:00:00+00:00"
        p.write_text(json.dumps(blob))
    server.set_guard(Guard(transport=httpx.MockTransport(lambda r: httpx.Response(503)), backoff=0, min_interval={}))
    r = await server.get_fsa_status("00100200")
    assert all(s["served_stale_cache"] for s in r["sources"]) and r["warnings"]


@pytest.mark.parametrize("bad", ["1193000", "0999010a", "099901000", "../../etc", "", "0999010 ", "09990100; DROP"])
async def test_bad_opeid_rejected_before_network(upstream, bad):
    try:
        res = await server.mcp.call_tool("get_fsa_status", {"opeid": bad})
        failed = bool(getattr(res, "is_error", False))
    except Exception:  # noqa: BLE001
        failed = True
    assert failed and not upstream.requests


def test_parsers_reject_garbage_and_bombs():
    with pytest.raises(fsa.ParseError):
        fsa.parse_hcm(b"not a zip")
    with pytest.raises(fsa.ParseError):
        fsa.parse_cdr(b"PK\x03\x04garbage")
    with pytest.raises(fsa.ParseError):
        fsa.parse_hcm(zip_bomb_xlsx())
    with pytest.raises(fsa.ParseError):
        fsa.parse_composite(b"<html>nope</html>")
    assert fsa.parse_composite(composite_xls())["rows"][0]["composite_score"] == 2.2


async def test_oversized_download_rejected(upstream):
    upstream.files[HCM_PATH] = b"0" * (fsa.MAX_FILE_BYTES + 10)
    with pytest.raises(UpstreamError, match="size limit"):
        await server.get_fsa_status("00100200")


async def test_disallowed_host_and_redirects():
    g = Guard(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})), min_interval={})
    with pytest.raises(UpstreamError, match="allowlist"):
        await g.get_json("https://evil.example.com/x")
    seen = []

    def handler(req):
        seen.append(req.url.host)
        return httpx.Response(302, headers={"location": "https://evil.example.com/x.xlsx"})

    g = Guard(transport=httpx.MockTransport(handler), min_interval={})
    with pytest.raises(UpstreamError, match="allowlist"):
        await g.get_bytes("https://studentaid.gov/sites/default/files/a.xlsx")
    assert seen == ["studentaid.gov"]


@pytest.mark.parametrize("bad", ["../x.json", "/etc/passwd", "a/b.json", "x.json/../../y.json", "X.json", ""])
def test_cache_traversal_rejected(tmp_path, monkeypatch, bad):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    with pytest.raises(ValueError):
        cache.safe_path(bad)


def test_cache_tamper_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    cache.write("a.json", {"k": 1}, "x", "https://x", file_sha256="abc")
    p = cache.safe_path("a.json")
    p.write_text(p.read_text().replace('"k":1', '"k":2'))
    assert cache.read("a.json") is None
