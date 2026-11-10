import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

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


async def test_missing_composite_score_reason_does_not_blame_public_status_alone(upstream):
    r = await server.get_title_iv_status("00100200")
    reason = next(n["reason"] for n in r["nulls"] if n["field"] == "financial_responsibility")
    assert "public institutions are not scored" in reason and "can also be missing" in reason and "does not state" in reason


async def test_status_for_listed_scored_and_missing(upstream):
    d = (await server.get_title_iv_status("00100200"))["data"]
    assert d["heightened_cash_monitoring"]["listed"] and d["heightened_cash_monitoring"]["as_of"] == "2026-06-01"
    assert d["financial_responsibility"] is None
    assert d["cohort_default_rates"]["entries"][0]["rates"][0]["rate_percent"] == 0.8
    assert [r["opeid"] for r in d["heightened_cash_monitoring"]["other_campuses_same_opeid6_listed"]] == ["00100201"]

    r = await server.get_title_iv_status("00884300")
    assert r["data"]["financial_responsibility"]["composite_score"] == 2.2
    assert r["data"]["financial_responsibility"]["fiscal_year_end"] == "2023-05-31"
    assert r["data"]["heightened_cash_monitoring"]["listed"] is False

    r = await server.get_title_iv_status("09990100")
    assert {n["field"] for n in r["nulls"]} == {"financial_responsibility", "cohort_default_rates"}
    assert all(n["reason"] for n in r["nulls"])
    for k in ("source", "source_url", "as_of", "retrieved_at"):
        assert r[k]
    assert len(r["sources"]) == 3 and all(s["file_sha256"] for s in r["sources"])


async def test_free_text_is_data_only(upstream):
    r = await server.get_title_iv_status("00100200")
    tools = await server.mcp.list_tools()
    assert all("Ignore previous" not in (t.description or "") for t in tools)
    assert "Ignore previous instructions" in json.dumps(r["data"])  # returned as a data field
    assert "untrusted" in r["notice"]


async def test_second_call_uses_cache(upstream):
    await server.get_title_iv_status("00100200")
    n = len(upstream.requests)
    await server.get_title_iv_status("00884300")
    assert len(upstream.requests) == n


async def test_stale_cache_served_when_refresh_fails(upstream):
    await server.get_title_iv_status("00100200")
    for name in ("fsa-hcm.json", "fsa-composite.json", "fsa-cdr.json"):
        p = cache.safe_path(name)
        blob = json.loads(p.read_text())
        blob["meta"]["retrieved_at"] = "2020-01-01T00:00:00+00:00"
        p.write_text(json.dumps(blob))
    server.set_guard(Guard(transport=httpx.MockTransport(lambda r: httpx.Response(503)), backoff=0, min_interval={}))
    r = await server.get_title_iv_status("00100200")
    assert all(s["served_stale_cache"] for s in r["sources"]) and r["warnings"]


@pytest.mark.parametrize("bad", ["9990100", "0999010a", "099901000", "../../etc", "", "0999010 ", "09990100; DROP", "０１１９３０００"])
async def test_bad_opeid_rejected_before_network(upstream, bad):
    try:
        res = await server.mcp.call_tool("get_title_iv_status", {"opeid": bad})
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
    r = await server.get_title_iv_status("00100200")  # the oversized file is refused; the other two sections are still returned
    n = next(x for x in r["nulls"] if x["field"] == "heightened_cash_monitoring")
    assert n["kind"] == "source_unavailable" and "size limit" in n["reason"] and r["data"]["heightened_cash_monitoring"] is None
    assert r["data"]["cohort_default_rates"] is not None and any("1 of the 3" in w for w in r["warnings"])
    for k in (HCM_PATH, COMP_PATH, CDR_PATH):
        upstream.files[k] = b"0" * (fsa.MAX_FILE_BYTES + 10)
    cache.safe_path("fsa-cdr.json").unlink()
    cache.safe_path("fsa-composite.json").unlink()
    with pytest.raises(ToolError, match="None of the three"):
        await server.get_title_iv_status("00100200")


async def test_a_file_that_is_slow_to_download_leaves_a_null_while_the_others_are_returned(upstream, monkeypatch):
    import asyncio

    from highered_risk import bounded

    monkeypatch.setattr(bounded, "DEADLINE", 0.2)
    real = fsa.composite

    async def slow(g):
        await asyncio.sleep(0.5)
        return await real(g)

    monkeypatch.setattr(fsa, "composite", slow)
    r = await server.get_title_iv_status("09990100")
    n = next(x for x in r["nulls"] if x["field"] == "financial_responsibility")
    assert n["kind"] == "source_unavailable" and "time limit" in n["reason"]
    assert r["data"]["heightened_cash_monitoring"]["listed"] is False  # the two quick files were read
    assert [x["field"] for x in r["nulls"] if x["kind"] == "source_unavailable"] == ["financial_responsibility"]
    await asyncio.sleep(0.6)  # it finishes in the background and is cached
    monkeypatch.setattr(fsa, "composite", real)
    later = await server.get_title_iv_status("09990100")
    assert not [x for x in later["nulls"] if x["kind"] == "source_unavailable"]


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


async def test_default_rate_rule_is_quoted_with_citation_and_not_about_the_institution(upstream):
    r = await server.get_title_iv_status("09990100")
    rule = r["data"]["reference"]["cohort_default_rate_sanction_rule"]
    assert rule["citation"] == "34 CFR 668.206(a)" and rule["url"].startswith("https://www.ecfr.gov/")
    assert "greater than 40 percent" in rule["loss_of_direct_loan_eligibility"] and "30 percent or greater" in rule["loss_of_direct_loan_and_pell_eligibility"]
    assert "not an assessment" in rule["note"]
