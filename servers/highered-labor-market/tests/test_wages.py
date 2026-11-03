import io
import json
import zipfile

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_labor_market import bounded, cache, server
from highered_labor_market.http import Guard
from highered_labor_market.sources import oews
from highered_labor_market.sources._xlsx import ParseError

from .conftest import CONTACT, oews_metro_rows, oews_row, oews_state_rows, oews_zip


async def rejected(name, args):
    try:
        res = await server.mcp.call_tool(name, args)
        return bool(getattr(res, "is_error", False))
    except Exception:  # noqa: BLE001
        return True


async def test_state_wages_match_the_published_row_and_carry_the_notice(upstream):
    r = await server.get_wages("29-1141", state="NM")
    w = r["data"]["wages"]
    assert (w["area"]["title"], w["area"]["kind"], w["occupation"]) == ("New Mexico", "state", "Registered Nurses")
    assert w["employment"]["estimate"] == 17980 and w["employment"]["relative_standard_error_pct"] == 1.8
    assert (w["annual"]["p10"], w["annual"]["p25"], w["annual"]["median"], w["annual"]["p75"], w["annual"]["p90"], w["annual"]["mean"]) == (74300, 80960, 94340, 102750, 123540, 95290)
    assert w["hourly"]["median"] == 45.36 and w["mean_wage"]["relative_standard_error_pct"] == 0.4 and r["data"]["release"] == "May 2025"
    assert any("cannot vouch" in x for x in r["warnings"]) and any("not recent graduates" in x for x in r["warnings"])
    for k in ("source", "source_url", "as_of", "retrieved_at"):
        assert r[k]
    assert r["source_url"].endswith("/oes/special-requests/oesm25st.zip") and "May 2025" in r["as_of"]


async def test_metro_wages_by_the_cbsa_code_in_the_institution_directory(upstream):
    w = (await server.get_wages("29-1141", area_code="22140"))["data"]["wages"]
    assert w["area"] == {"code": "22140", "title": "Farmington, NM", "state": "NM", "kind": "metropolitan area"} and w["annual"]["median"] == 83070 and w["employment"]["estimate"] == 840
    b = (await server.get_wages("29-1141", area_code="14460"))["data"]["wages"]
    assert b["annual"]["median"] == 106180 and b["employment"]["estimate"] == 64240


async def test_nonmetropolitan_codes_keep_their_leading_zero(upstream):
    w = (await server.get_wages("29-1141", area_code="0100001"))["data"]["wages"]
    assert w["area"]["kind"] == "nonmetropolitan area" and w["area"]["state"] == "AL" and w["annual"]["median"] == 60000
    assert (await server.get_wages("29-1141", state="AL"))["data"]["wages"]["annual"]["median"] == 70000  # state code 1 is stored without the zero


async def test_markers_become_nulls_with_a_kind_and_never_zero(upstream):
    r = await server.get_wages("29-2061", state="NM")
    w = r["data"]["wages"]
    assert w["annual"]["median"] is None and w["annual"]["mean"] is None and w["hourly"]["median"] is None and w["employment"]["estimate"] == 1990
    kinds = {n["field"]: n["kind"] for n in r["nulls"]}
    assert kinds["annual.median"] == "suppressed" and kinds["mean_wage.relative_standard_error_pct"] == "suppressed"
    assert any("did not publish" in n["reason"] for n in r["nulls"])
    e = await server.get_wages("11-1011", state="NM")
    assert e["data"]["wages"]["employment"]["estimate"] is None and any(n["field"] == "employment.estimate" and n["kind"] == "suppressed" for n in e["nulls"])


async def test_top_coded_wages_are_the_top_code_flagged_as_a_floor(upstream):
    r = await server.get_wages("11-1011", state="NM")
    w = r["data"]["wages"]
    assert w["annual"]["mean"] == 239200 and w["annual"]["p90"] == 239200 and w["hourly"]["median"] == 115.0
    assert set(w["top_coded"]) == {"annual.mean", "annual.p75", "annual.p90", "hourly.mean", "hourly.median"} and any("at least that" in x for x in r["warnings"])
    assert not any(n["field"] in w["top_coded"] for n in r["nulls"])


async def test_unknown_area_and_unlisted_occupation_are_nulls_with_reasons(upstream):
    r = await server.get_wages("29-1141", area_code="99999")
    assert r["data"]["wages"] is None and r["nulls"][0]["kind"] == "not_found" and "search_metros" in r["nulls"][0]["reason"]
    r2 = await server.get_wages("99-9999", area_code="22140")
    assert r2["data"]["wages"] is None and "too few reports" in r2["nulls"][0]["reason"]


async def test_exactly_one_of_state_or_area(upstream):
    for args in ({"soc": "29-1141"}, {"soc": "29-1141", "state": "NM", "area_code": "22140"}):
        with pytest.raises(ToolError, match="exactly one"):
            await server.get_wages(**args)


async def test_search_metros(upstream):
    r = await server.search_metros("farm")
    assert [a["title"] for a in r["data"]["areas"]] == ["Farmington, NM"] and r["data"]["areas"][0]["area_code"] == "22140"
    n = await server.search_metros("nonmetropolitan", state="AL")
    assert [a["area_code"] for a in n["data"]["areas"]] == ["0100001"] and n["data"]["areas"][0]["kind"] == "nonmetropolitan area"
    none = await server.search_metros("Atlantis")
    assert none["data"]["areas"] == [] and none["nulls"][0]["kind"] == "not_found"


async def test_only_detailed_occupations_with_valid_codes_are_kept(upstream):
    L = await oews.get(server.guard(), "st")
    rows = L.data["areas"]["35"]["rows"]
    assert set(rows) == {"29-1141", "29-2061", "11-1011"}  # the major group row and the malformed code were dropped


async def test_the_second_call_uses_the_cache_and_a_stale_copy_is_served_if_refresh_fails(upstream, monkeypatch):
    await server.get_wages("29-1141", state="NM")
    n = len([q for q in upstream.requests if q.url.path.startswith("/oes/")])
    await server.get_wages("29-1141", state="MA")
    assert len([q for q in upstream.requests if q.url.path.startswith("/oes/")]) == n
    monkeypatch.setattr(oews, "load", oews.load)  # keep the real loader; age the cache instead
    monkeypatch.setattr("highered_labor_market.sources._load.cache.is_fresh", lambda meta, ttl_days=0: False)
    upstream.oews_page = "<html>gone</html>"
    again = await server.get_wages("29-1141", state="NM")
    assert again["data"]["wages"]["annual"]["median"] == 94340 and again["sources"][0]["served_stale_cache"] is True


def test_newest_year_is_taken_from_links_on_the_bls_host_only():
    page = ('<a href="/oes/special-requests/oesm24st.zip">a</a> <a href="/oes/special-requests/oesm25st.zip">b</a> '
            '<a href="https://evil.example/oes/special-requests/oesm26st.zip">c</a> <a href="//evil.example/oes/special-requests/oesm27st.zip">d</a> '
            '<a href="/oes/special-requests/oesm25ma.zip">e</a> <a href="/oes/special-requests/../oesm28st.zip">f</a>')
    assert oews.newest(page, "st") == "25" and oews.newest(page, "ma") == "25"
    with pytest.raises(ParseError):
        oews.newest("<html>nothing</html>", "st")


def test_archive_reading_is_exact_and_bounded():
    good = oews_zip("st", oews_state_rows(), decoys=["oesm25st/other.xlsx"])
    assert oews.read_member(good, "oesm25st/state_M2025_dl.xlsx")[:2] == b"PK"
    with pytest.raises(ParseError, match="expected workbook"):
        oews.read_member(oews_zip("st", oews_state_rows(), member="oesm25st/../state_M2025_dl.xlsx"), "oesm25st/state_M2025_dl.xlsx")
    with pytest.raises(ParseError, match="expected workbook"):
        oews.read_member(oews_zip("st", oews_state_rows(), member="elsewhere/state_M2025_dl.xlsx"), "oesm25st/state_M2025_dl.xlsx")
    with pytest.raises(ParseError, match="not a valid zip"):
        oews.read_member(b"not a zip", "x")
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("oesm25st/state_M2025_dl.xlsx", b"0" * (oews.MAX_UNPACKED + 1))
    with pytest.raises(ParseError, match="safety limit"):
        oews.read_member(bomb.getvalue(), "oesm25st/state_M2025_dl.xlsx")
    many = io.BytesIO()
    with zipfile.ZipFile(many, "w") as z:
        for i in range(25):
            z.writestr(f"f{i}", b"x")
    with pytest.raises(ParseError, match="safety limit"):
        oews.read_member(many.getvalue(), "f0")


def test_a_workbook_missing_columns_or_rows_is_refused():
    from .conftest import xlsx

    with pytest.raises(ParseError, match="expected columns"):
        oews.parse(xlsx({"s": [["AREA", "OCC_CODE"], ["35", "29-1141"]]}), "st")
    with pytest.raises(ParseError, match="no detailed occupation rows"):
        oews.parse(xlsx({"s": [oews_row.__globals__["OEWS_COLS"]]}), "st")


async def test_an_oversized_download_and_a_non_zip_are_refused(upstream):
    upstream.oews["st"] = b"0" * (oews.MAX_ZIP["st"] + 10)
    with pytest.raises(ToolError, match="size limit"):
        await server.get_wages("29-1141", state="NM")
    upstream.oews["st"] = b"<html>login</html>"
    with pytest.raises(ToolError, match="not a valid zip"):
        await server.get_wages("29-1141", state="NM")


@pytest.mark.parametrize("name,args", [
    ("get_wages", {"soc": "291141", "state": "NM"}), ("get_wages", {"soc": "29-1141", "state": "XX"}), ("get_wages", {"soc": "29-1141", "area_code": "2214"}),
    ("get_wages", {"soc": "29-1141", "area_code": "221400"}), ("get_wages", {"soc": "29-1141", "area_code": "22140 "}), ("get_wages", {"soc": "29-1141", "area_code": "２２１４０"}),
    ("get_wages", {"soc": "29-1141", "area_code": "22140; drop"}), ("get_wages", {"soc": "29-114１", "state": "NM"}), ("get_wages", {"soc": "29-1141/../x", "state": "NM"}),
    ("search_metros", {"name_contains": "x"}), ("search_metros", {"name_contains": "x" * 61}), ("search_metros", {"name_contains": "<script>"}),
    ("search_metros", {"name_contains": "Farm\nington"}), ("search_metros", {"name_contains": "Farmington", "state": "ZZ"}),
])
async def test_bad_inputs_are_rejected_before_any_request(upstream, name, args):
    assert await rejected(name, args) and not upstream.requests


async def test_a_redirect_to_another_host_is_refused_and_the_contact_goes_to_bls_only(upstream):
    def handler(req):
        if req.url.host == "www.bls.gov" and req.url.path == "/oes/tables.htm":
            return httpx.Response(302, headers={"location": "https://evil.example/oes/tables.htm"})
        return httpx.Response(200, text="x")

    server.set_guard(Guard(transport=httpx.MockTransport(handler), backoff=0, min_interval={}))
    with pytest.raises(ToolError, match="not allowed|Blocked"):
        await server.get_wages("29-1141", state="NM")
    assert not any(q.url.host == "evil.example" for q in upstream.requests)


async def test_the_contact_address_is_required_sent_to_bls_only_and_never_returned(upstream, monkeypatch):
    r = await server.get_wages("29-1141", state="NM")
    assert CONTACT not in json.dumps(r)
    sent = [q for q in upstream.requests if q.url.path.startswith("/oes/")]
    assert sent and all(CONTACT in q.headers["user-agent"] for q in sent)
    monkeypatch.delenv("HIGHERED_MCPS_CONTACT")
    cache.safe_path("oews-metro.json")  # path check only; no cache exists for metros yet
    with pytest.raises(ToolError, match="HIGHERED_MCPS_CONTACT"):
        await server.get_wages("29-1141", area_code="22140")


async def test_a_first_download_past_the_deadline_says_so_and_finishes_later(upstream, monkeypatch):
    import asyncio

    monkeypatch.setattr(bounded, "DEADLINE", 0.1)
    real = oews.get

    async def slow(g, kind):
        await asyncio.sleep(0.4)
        return await real(g, kind)

    monkeypatch.setattr(oews, "get", slow)
    with pytest.raises(ToolError, match="downloaded for the first time"):
        await server.get_wages("29-1141", state="NM")
    await asyncio.sleep(0.6)
    monkeypatch.setattr(bounded, "DEADLINE", 45.0)
    monkeypatch.setattr(oews, "get", real)
    assert (await server.get_wages("29-1141", state="NM"))["data"]["wages"]["annual"]["median"] == 94340


async def test_the_tools_have_no_person_or_text_search_inputs(upstream):
    schemas = {t.name: set(t.input_schema["properties"]) for t in await server.mcp.list_tools() if t.name in ("get_wages", "search_metros")}
    assert schemas == {"get_wages": {"soc", "state", "area_code"}, "search_metros": {"name_contains", "state"}}


async def test_the_metro_archive_is_read_as_two_workbooks_metropolitan_and_nonmetropolitan(upstream):
    """Found in the question test rerun: the BOS workbook is the nonmetropolitan areas, not a New England file, and was not being read."""
    L = await oews.get(server.guard(), "ma")
    kinds = {a["type"] for a in L.data["areas"].values()}
    assert kinds == {"4", "6"} and "22140" in L.data["areas"] and "3500001" in L.data["areas"] and "0100001" in L.data["areas"]
    assert oews.member_names("ma", "25") == ["oesm25ma/MSA_M2025_dl.xlsx", "oesm25ma/BOS_M2025_dl.xlsx"] and oews.member_names("st", "25") == ["oesm25st/state_M2025_dl.xlsx"]


async def test_a_metro_archive_without_the_nonmetropolitan_workbook_is_refused(upstream):
    upstream.oews["ma"] = oews_zip("ma", oews_metro_rows(), with_bos=False)
    with pytest.raises(ToolError, match="expected workbook"):
        await server.get_wages("29-1141", area_code="22140")


async def test_nonmetropolitan_wages_and_search_come_from_the_second_workbook(upstream):
    w = (await server.get_wages("29-1141", area_code="3500001"))["data"]["wages"]
    assert w["area"]["kind"] == "nonmetropolitan area" and w["annual"]["median"] == 78000
    found = await server.search_metros("nonmetropolitan", state="NM")
    assert [a["area_code"] for a in found["data"]["areas"]] == ["3500001"]
