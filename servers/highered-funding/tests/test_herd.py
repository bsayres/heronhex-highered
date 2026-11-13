import io
import zipfile

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_funding import cache, server
from highered_funding.http import Guard, UpstreamError
from highered_funding.sources import herd

from .conftest import PSU, herd_zip


def test_discovery_uses_only_the_pages_own_safe_links():
    files = herd.pick_files(__import__("tests.conftest", fromlist=["x"]).HERD_PAGE)
    assert set(files) == {2022, 2023, 2024} and files[2024]["short"].endswith("2024_short.zip")
    with pytest.raises(herd.ParseError):
        herd.pick_files('<a href="/../../x/higher_education_r_and_d_2030.zip">x</a>')


async def test_spend_converts_thousands_and_labels_imputed(upstream):
    r = await server.get_research_spend("214777", years=2)
    d = r["data"]
    assert d["columns"][:3] == ["year", "form", "federal"] and d["units"] == "US dollars"
    row24 = next(x for x in d["rows"] if x[0] == 2024)
    assert row24[2] == 858_666_000 and row24[8] == 1_302_971_000 and row24[9] is False  # thousands -> dollars
    assert [x[0] for x in d["rows"]] == [2023, 2024]
    for k in ("source", "source_url", "as_of", "retrieved_at"):
        assert r[k]
    assert len(r["sources"]) == 2 and all(s["file_sha256"] for s in r["sources"])


async def test_short_form_institution_is_found_and_imputed_flagged(upstream):
    r = await server.get_research_spend("222222", years=1)
    assert r["data"]["rows"][0][1] == "short" and r["data"]["rows"][0][8] == 90_000
    r = await server.get_research_spend("111111", years=1)
    assert r["data"]["rows"][0][9] is True and any("imputed" in w for w in r["warnings"])
    assert r["data"]["rows"][0][4] is None  # a source line not reported is null, not zero


async def test_absent_institution_is_null_with_reason_and_unjoined_hint(upstream):
    r = await server.get_research_spend("999001", years=1, state="NH")
    assert r["data"]["rows"] == [] and "150,000" in r["nulls"][0]["reason"]
    assert [x["name"] for x in r["data"]["unjoined_herd_entries"]] == ["Unjoinable Tech"] and any("cannot be joined" in w for w in r["warnings"])
    r = await server.get_research_spend("999001", years=1)  # no state: no hint, no name join
    assert r["data"]["unjoined_herd_entries"] == []


async def test_second_call_uses_cache_and_stale_is_served_on_failure(upstream):
    await server.get_research_spend("214777", years=1)
    n = len(upstream.requests)
    await server.get_research_spend("111111", years=1)
    assert len(upstream.requests) == n
    for name in ("herd-2024.json", "herd-index.json"):
        p = cache.safe_path(name)
        blob = __import__("json").loads(p.read_text())
        blob["meta"]["retrieved_at"] = "2020-01-01T00:00:00+00:00"
        p.write_text(__import__("json").dumps(blob))
    server.set_guard(Guard(transport=httpx.MockTransport(lambda r: httpx.Response(503)), backoff=0, min_interval={}))
    r = await server.get_research_spend("214777", years=1)
    assert r["sources"][0]["served_stale_cache"] and any("cached copy" in w for w in r["warnings"])


def test_zip_defences():
    with pytest.raises(herd.ParseError):
        herd.parse_zip(b"not a zip", 2024, "standard")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("other.csv", "a,b\n1,2\n")
    with pytest.raises(herd.ParseError, match="expected file"):
        herd.parse_zip(buf.getvalue(), 2024, "standard")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("herd2024.csv", "inst_id,year\n1,2024\n")
    with pytest.raises(herd.ParseError, match="columns"):
        herd.parse_zip(buf.getvalue(), 2024, "standard")


def test_decompressed_size_is_capped_while_streaming(monkeypatch):
    monkeypatch.setattr(herd, "MAX_CSV_BYTES", 2_000)
    big = herd_zip(2024, "standard", [PSU] * 50)
    with pytest.raises(herd.ParseError, match="size limit"):
        herd.parse_zip(big, 2024, "standard")


async def test_oversized_download_rejected(upstream, monkeypatch):
    monkeypatch.setattr(herd, "MAX_ZIP_BYTES", 500)
    with pytest.raises((ToolError, UpstreamError), match="size limit|could not be retrieved"):
        await server.get_research_spend("214777", years=1)


async def test_a_cold_multi_year_request_fetches_the_file_list_once(upstream):
    """Several HERD years start together; they must share one request for the NCSES page and one index write, not one each."""
    r = await server.get_research_spend("214777", years=3)
    assert len(r["data"]["rows"]) >= 2
    pages = [q for q in upstream.requests if q.url.host == "ncses.nsf.gov" and q.url.path.startswith("/explore-data")]
    assert len(pages) == 1


@pytest.mark.parametrize("bad", ["16777", "1677311", "16773a", "../../x", "", "167731; DROP", "１６７７３１"])
async def test_bad_unitid_rejected_before_network(upstream, bad):
    try:
        res = await server.mcp.call_tool("get_research_spend", {"unitid": bad})
        failed = bool(getattr(res, "is_error", False))
    except Exception:  # noqa: BLE001
        failed = True
    assert failed and not upstream.requests
