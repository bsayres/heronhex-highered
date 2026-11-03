import asyncio
import io
import json
import zipfile

import httpx
import pytest
from conftest import EF_HEADER, ef_csv, ef_row, ef_zip
from mcp.server.mcpserver.exceptions import ToolError

from highered_institutions import bounded, cache
from highered_institutions import server as s
from highered_institutions.http import Guard, UpstreamError
from highered_institutions.sources import ipeds

COLS = ["fall_year", *ipeds.COLUMNS]


def table(r):
    return {row[0]: dict(zip(COLS, row)) for row in r["data"]["rows"]}


async def rejected(args):
    try:
        res = await s.mcp.call_tool("get_retention", args)
        return bool(getattr(res, "is_error", False))
    except Exception:  # noqa: BLE001
        return True


async def test_Test College A_rates_cohorts_and_flags_as_published(upstream):
    r = await s.get_retention("999001", years=2)
    t = table(r)
    a = t[2023]
    assert (a["ft_rate_pct"], a["ft_retained"], a["ft_cohort"], a["ft_flag"]) == (39, 42, 108, "R")
    assert (a["pt_rate_pct"], a["pt_retained"], a["pt_cohort"], a["pt_flag"], a["student_faculty_ratio"]) == (21, 21, 99, "R", 14)
    assert round(42 / 108 * 100) == a["ft_rate_pct"]  # the published rate is not recomputed, but the counts support it
    b = t[2022]  # the revised file wins over the provisional one beside it
    assert (b["ft_rate_pct"], b["ft_retained"], b["ft_cohort"], b["pt_flag"]) == (41, 50, 122, "L")
    assert r["data"]["flag_meanings"]["R"] == "Reported" and r["data"]["flag_meanings"]["L"].startswith("Imputed")
    assert "same institution" in r["data"]["definition"]
    assert len(r["sources"]) == 2 and r["sources"][0]["source_url"].endswith("EF2023D.zip") and "fall 2023 collection" in r["sources"][0]["as_of"]
    for k in ("source", "source_url", "as_of", "retrieved_at"):
        assert r[k]
    assert any("not a graduation rate" in w for w in r["warnings"]) and any("not plain reported" in w for w in r["warnings"])


async def test_the_newest_published_year_is_found_and_remembered(upstream):
    r = await s.get_retention("999001", years=1)
    assert list(table(r)) == [2023]
    probes = [q for q in upstream.requests if q.url.host == "nces.ed.gov"]
    assert len(probes) >= 2 and probes[0].url.path.endswith("2026D.zip") or probes[0].url.path.endswith("EF2026D.zip")
    n = len(probes)
    await s.get_retention("999001", years=1)
    assert len([q for q in upstream.requests if q.url.host == "nces.ed.gov"]) == n  # the year and the table are cached


async def test_years_before_the_files_exist_are_nulls_not_errors(upstream):
    r = await s.get_retention("999001", years=4)
    assert sorted(table(r)) == [2022, 2023]
    gone = [n for n in r["nulls"] if n["kind"] == "not_found"]
    assert {n["field"] for n in gone} == {"FY2021", "FY2020"} and "has not published" in gone[0]["reason"]


async def test_not_applicable_blank_and_unknown_flags_become_nulls_with_a_kind(upstream):
    sj = await s.get_retention("999003", years=1)  # Test University C: no part-time cohort (flag A)
    n = next(n for n in sj["nulls"] if n["field"] == "part_time_retention_rate[2023]")
    assert n["kind"] == "not_applicable" and "Not applicable" in n["reason"] and table(sj)[2023]["ft_rate_pct"] == 78
    blank = await s.get_retention("111111", years=1)
    kinds = {n["field"]: n["kind"] for n in blank["nulls"]}
    assert kinds["full_time_retention_rate[2023]"] == "not_reported" and kinds["part_time_retention_rate[2023]"] == "not_reported"
    assert any("left item blank" in n["reason"] for n in blank["nulls"]) and any("not derived" in n["reason"] for n in blank["nulls"])
    upstream.ef[2023] = ipeds_zip_with_flag("999001", "Q")
    cache.safe_path("ipeds-ef2023d.json").unlink()
    odd = await s.get_retention("999001", years=1)
    assert any("not in IPEDS's dictionary" in n["reason"] for n in odd["nulls"])


def ipeds_zip_with_flag(unitid, flag):
    return ef_zip(2023, [ef_row(unitid, ft=("", "", "", flag))])


async def test_an_institution_missing_from_every_file_is_a_null_per_year_and_not_an_error(upstream):
    r = await s.get_retention("999999", years=2)
    assert r["data"]["rows"] == [] and {n["field"] for n in r["nulls"] if n["kind"] == "not_reported"} == {"FY2023", "FY2022"}
    assert "not in the IPEDS 2023 retention file" in r["nulls"][0]["reason"]


async def test_imputed_student_faculty_ratio_is_flagged(upstream):
    r = await s.get_retention("999002", years=1)
    a = table(r)[2023]
    assert (a["ft_rate_pct"], a["ft_retained"], a["ft_cohort"], a["student_faculty_ratio"], a["ratio_flag"]) == (62, 178, 285, 12, "J")
    assert any("2023" in w and "not plain reported" in w for w in r["warnings"])


async def test_it_does_not_touch_urban_so_it_still_answers_when_urban_is_down(upstream, monkeypatch):
    def down(req):
        if req.url.host == "educationdata.urban.org":
            return httpx.Response(500)
        return upstream(req)

    s.set_guard(Guard(transport=httpx.MockTransport(down), backoff=0, min_interval={}))
    r = await s.get_retention("999001", years=1)
    assert table(r)[2023]["ft_rate_pct"] == 39
    assert not [q for q in upstream.requests if q.url.host == "educationdata.urban.org"]


@pytest.mark.parametrize("args", [
    {"unitid": "16763"}, {"unitid": "9990011"}, {"unitid": "ABCDEF"}, {"unitid": "１６７６３１"}, {"unitid": "999001 "}, {"unitid": "999001; DROP"}, {"unitid": ""},
    {"unitid": "999001", "years": 0}, {"unitid": "999001", "years": 9}, {"unitid": "999001", "years": "5; rm"}, {"unitid": "999001", "years": -1},
])
async def test_bad_inputs_are_rejected_before_any_request(upstream, args):
    assert await rejected(args) and not upstream.requests


def test_archive_reading_is_exact_and_bounded():
    good = ef_zip(2023, [ef_row("999001")], extra=[("ef2023d_extra.csv", "x"), ("readme.txt", "x")])
    assert ipeds.read_member(good, 2023)[:3] == b"\xef\xbb\xbf"
    for bad in ("../ef2023d.csv", "sub/ef2023d.csv", "EF2023D.csv", "ef2023d.csv.exe", "ef2022d.csv", "ef2023d.csv/"):
        with pytest.raises(ipeds.ParseError, match="expected data file"):
            ipeds.read_member(ef_zip(2023, [ef_row("999001")], member=bad), 2023)
    with pytest.raises(ipeds.ParseError, match="not a valid zip"):
        ipeds.read_member(b"<html>login</html>", 2023)
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("ef2023d.csv", b"0" * (ipeds.MAX_UNPACKED + 1))
    with pytest.raises(ipeds.ParseError, match="safety limit"):
        ipeds.read_member(bomb.getvalue(), 2023)
    many = io.BytesIO()
    with zipfile.ZipFile(many, "w") as z:
        for i in range(12):
            z.writestr(f"f{i}.csv", b"x")
    with pytest.raises(ipeds.ParseError, match="safety limit"):
        ipeds.read_member(many.getvalue(), 2023)


def test_a_file_with_missing_columns_or_no_rows_or_junk_ids_is_refused():
    with pytest.raises(ipeds.ParseError, match="expected columns"):
        ipeds.parse(ef_csv([ef_row("999001")], header=[c for c in EF_HEADER if c != "RET_PCF"]).encode())
    with pytest.raises(ipeds.ParseError, match="no institution rows"):
        ipeds.parse(ef_csv([ef_row("12345"), ef_row("abc123"), ef_row("<script>")]).encode())
    with pytest.raises(ipeds.ParseError, match="empty"):
        ipeds.parse(b"")
    parsed = ipeds.parse(ef_csv([ef_row("999001"), ef_row("not-an-id")]).encode())
    assert list(parsed["rows"]) == ["999001"]


async def test_an_oversized_or_non_zip_download_is_refused(upstream):
    upstream.ef[2023] = b"0" * (ipeds.MAX_ZIP + 10)
    with pytest.raises(UpstreamError, match="size limit"):
        await ipeds.year_table(s.guard(), 2023)
    upstream.ef[2023] = b"<html>login</html>"
    with pytest.raises(ipeds.ParseError, match="not a valid zip"):
        await ipeds.year_table(s.guard(), 2023)


async def test_only_nces_is_contacted_and_other_hosts_and_redirects_are_refused(upstream):
    def handler(req):
        if req.url.host == "nces.ed.gov":
            return httpx.Response(302, headers={"location": "https://evil.example/EF2023D.zip"})
        return httpx.Response(200, content=b"x")

    g = Guard(transport=httpx.MockTransport(handler), backoff=0, min_interval={})
    with pytest.raises(UpstreamError, match="allowlist"):
        await g.get_bytes("https://nces.ed.gov/ipeds/datacenter/data/EF2023D.zip")
    with pytest.raises(UpstreamError, match="allowlist"):
        await g.get_bytes("https://evil.example/EF2023D.zip")
    with pytest.raises(UpstreamError, match="https"):
        await g.get_bytes("http://nces.ed.gov/ipeds/datacenter/data/EF2023D.zip")


async def test_year_bounds_and_cache_names_cannot_escape(upstream):
    for bad in (0, 1989, 2101, -5):
        with pytest.raises(UpstreamError, match="Invalid year"):
            await ipeds.year_table(s.guard(), bad)
    for name in ("../ipeds-ef2023d.json", "ipeds-ef2023d.json/../../x.json", "IPEDS.json"):
        with pytest.raises(ValueError):
            cache.safe_path(name)
    assert cache.safe_path("ipeds-ef2023d.json").parent == cache.cache_dir()


async def test_a_slow_first_download_says_so_and_finishes_later(upstream, monkeypatch):
    monkeypatch.setattr(bounded, "DEADLINE", 0.1)
    real = ipeds.latest_year

    async def slow(g):
        await asyncio.sleep(0.4)
        return await real(g)

    monkeypatch.setattr(ipeds, "latest_year", slow)
    with pytest.raises(ToolError, match="first time"):
        await s.get_retention("999001", years=1)
    await asyncio.sleep(0.6)
    monkeypatch.setattr(bounded, "DEADLINE", 45.0)
    monkeypatch.setattr(ipeds, "latest_year", real)
    assert table(await s.get_retention("999001", years=1))[2023]["ft_rate_pct"] == 39


async def test_the_response_has_no_secrets_and_the_tool_has_only_two_inputs(upstream):
    tool = next(t for t in await s.mcp.list_tools() if t.name == "get_retention")
    assert set(tool.input_schema["properties"]) == {"unitid", "years"} and tool.annotations.read_only_hint and tool.title
    blob = json.dumps(await s.get_retention("999001", years=1))
    assert "api_key" not in blob.lower() and "@" not in blob


async def test_rates_on_very_small_cohorts_are_warned_about(upstream):
    r = await s.get_retention("999003", years=2)  # Test University C's part-time fall 2022 cohort is one student
    w = [x for x in r["warnings"] if "fewer than 30" in x]
    assert w and "fall 2022 part-time (1 student)" in w[0] and "full-time" not in w[0]
    big = await s.get_retention("999001", years=2)
    assert not [x for x in big["warnings"] if "fewer than 30" in x]
