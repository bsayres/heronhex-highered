import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_labor_market import cache, server
from highered_labor_market.sources import bls, crosswalk, onet, scorecard

from .conftest import CONTACT, SC_KEY, bls_xlsx, crosswalk_xlsx, onet_files


def test_crosswalk_no_match_rows_become_unmatched_not_occupations():
    d = crosswalk.parse(crosswalk_xlsx())
    assert "01.0508" not in d["programs"] and "01.0508" in d["unmatched"]
    assert [s[0] for s in d["programs"]["51.3801"]["socs"]] == ["25-1072", "29-1141"]
    with pytest.raises(crosswalk.ParseError):
        crosswalk.parse(b"not an xlsx")


def test_bls_parse_keeps_line_items_only_and_looks_up_broad_groups():
    d = bls.parse(bls_xlsx())
    assert d["projection_period"] == "2025-35" and "31-0000" not in d["occupations"]
    assert bls.lookup(d["occupations"], "29-1141")[2] == "exact"
    rec, code, how = bls.lookup(d["occupations"], "31-1121")
    assert (code, how) == ("31-1120", "broad_group") and rec["entry_education"] == "High school diploma or equivalent"
    assert bls.lookup(d["occupations"], "99-1234")[2] == "none"


def test_onet_parse_drops_suppressed_ratings_and_keeps_only_core_tasks_and_hot_tech():
    d = onet.parse({k: v.encode() for k, v in onet_files().items()})
    rn = d["occupations"]["29-1141.00"]
    assert [s[0] for s in rn["essential_skills"]] == ["Active Listening", "Speaking"] and rn["essential_skills"][0] == ["Active Listening", 4.0, 4.25]
    assert len(rn["core_tasks"]) == 1 and rn["hot_technologies"] == [["Epic EHR", "Medical software"]]
    assert d["by_soc"]["29-1141"] == ["29-1141.00", "29-1141.01"]


def test_scorecard_normalizes_codes_and_drops_bad_levels():
    from .conftest import scorecard_json
    r = scorecard_json()["results"][0]["latest.programs.cip_4_digit"]
    progs = [p for x in r if (p := scorecard._program(x))]
    assert [p["cip4"] for p in progs] == ["51.38", "51.00", "01.01"] and progs[0]["earnings_1yr_median_institution"] is None


async def test_map_program_six_and_four_digit_and_no_match(upstream):
    r = await server.map_program_to_occupations("51.3801")
    assert [x[0] for x in r["data"]["rows"]] == ["25-1072", "29-1141"] and any("not based on empirical data" in w for w in r["warnings"])
    r = await server.map_program_to_occupations("51.38")
    assert [x[0] for x in r["data"]["rows"]] == ["25-1072", "29-1141"] and r["data"]["rows"][1][2] == ["51.3801", "51.3899"]
    r = await server.map_program_to_occupations("01.0508")
    assert r["data"]["rows"] == [] and "NO MATCH" in r["nulls"][0]["reason"]
    r = await server.map_program_to_occupations("99.9999")
    assert "not in the CIP" in r["nulls"][0]["reason"]
    for k in ("source", "source_url", "as_of", "retrieved_at"):
        assert r[k]


async def test_outlook_converts_thousands_and_flags_broad_group(upstream):
    r = await server.get_occupation_outlook("29-1141")
    o = r["data"]["outlook"]
    assert o["employment_base_year"] == 3_465_400 and o["annual_openings"] == 180_800 and o["median_annual_wage_usd"] == 97550 and o["bls_match"] == "exact"
    r = await server.get_occupation_outlook("31-1121")
    assert r["data"]["outlook"]["bls_match"] == "broad_group" and any("broad group 31-1120" in w for w in r["warnings"])
    r = await server.get_occupation_outlook("99-1234")
    assert r["data"]["outlook"] is None and r["nulls"][0]["field"] == "outlook"


async def test_skills_use_bulk_files_with_attribution_and_no_key(upstream):
    r = await server.get_occupation_skills("29-1141", top=5)
    d = r["data"]
    assert d["onet_code"] == "29-1141.00" and d["other_onet_occupations"] == [["29-1141.01", "Acute Care Nurses"]]
    assert "Suppressed Skill" not in json.dumps(d) and "O*NET 31.0 Database" in r["citation"] and "CC BY 4.0" in r["citation"]
    reqs = [q for q in upstream.requests if q.url.host == "www.onetcenter.org"]
    assert reqs and all("x-api-key" not in q.headers for q in reqs) and "db_31_0_csv" in str(reqs[-1].url)
    r = await server.get_occupation_skills("11-9999")
    assert r["data"]["onet_occupation"] is None


async def test_outcomes_label_suppression_and_never_substitute_national(upstream):
    r = await server.get_program_outcomes("999001")
    cols = r["data"]["columns"]
    rows = {x[0]: dict(zip(cols, x, strict=True)) for x in r["data"]["rows"]}
    assert rows["51.00"]["earnings_1yr_median_institution"] == 44854 and rows["51.38"]["earnings_1yr_median_institution"] is None
    assert rows["51.38"]["earnings_1yr_median_national"] == 75149 and rows["51.38"]["credential"] == "Associate's Degree"
    assert any(n["field"] == "earnings_1yr_median_institution" and "PS" in n["reason"] for n in r["nulls"])
    assert next(x[0] for x in r["data"]["rows"]) == "51.00"  # sorted by awards
    r = await server.get_program_outcomes("999001", credential=1)
    assert [x[0] for x in r["data"]["rows"]] == ["01.01"]
    r = await server.get_program_outcomes("999001", cip4="11.11")
    assert r["data"]["rows"] == [] and r["nulls"][0]["field"] == "programs"


async def test_scorecard_key_only_in_header_and_missing_key_fails_cleanly(upstream, monkeypatch):
    r = await server.get_program_outcomes("999001")
    reqs = [q for q in upstream.requests if q.url.host == "api.data.gov"]
    assert reqs and all(q.headers["x-api-key"] == SC_KEY and SC_KEY not in str(q.url) for q in reqs) and SC_KEY not in json.dumps(r)
    monkeypatch.delenv("COLLEGE_SCORECARD_API_KEY")
    upstream.requests.clear()
    r = await server.get_program_outcomes("999001")
    assert all(q.headers["x-api-key"] == "DEMO_KEY" and "DEMO_KEY" not in str(q.url) for q in upstream.requests if q.url.host == "api.data.gov")
    assert any("DEMO_KEY" in w for w in r["warnings"])
    with pytest.raises(ToolError, match="not found"):
        monkeypatch.setenv("COLLEGE_SCORECARD_API_KEY", SC_KEY)
        await server.get_program_outcomes("999999")


async def test_alignment_reports_ranges_not_a_score(upstream):
    r = await server.get_program_alignment("999001", "51.38", 2)
    d = r["data"]
    assert d["institution_program"]["awards_period_1"] == 8 and d["institution_program"]["earnings_1yr_median_institution"] is None
    s = d["openings_summary"]
    assert s["annual_openings_all_mapped"] == 189_300 and s["annual_openings_education_matched"] == 0 and s["occupations_mapped"] == 2
    assert not any(k in json.dumps(d) for k in ("score", "ratio", "gap"))
    assert any("does not mean no demand" in w for w in r["warnings"]) and any("not regional demand" in w for w in r["warnings"])
    rule = d["education_match_rule"]
    assert rule["bls_entry_education_counted_as_matching"] == ["Associate's degree"]
    r = await server.get_program_alignment("999001", "51.38", 3)
    assert r["data"]["openings_summary"]["annual_openings_education_matched"] == 180_800 and r["data"]["institution_program"] is None
    assert any(n["field"] == "program" for n in r["nulls"])


async def test_alignment_counts_broad_bls_group_once_and_degrades_without_bls(upstream, monkeypatch):
    r = await server.get_program_alignment("999001", "51.39", 1)
    s = r["data"]["openings_summary"]
    assert s["occupations_mapped"] == 2 and s["distinct_bls_rows_counted"] == 1 and s["annual_openings_all_mapped"] == 847_300
    assert any("share a BLS row" in w for w in r["warnings"])
    monkeypatch.delenv("HIGHERED_MCPS_CONTACT")
    server.set_guard(server.Guard(transport=httpx.MockTransport(upstream), backoff=0, min_interval={}))
    cache_file = cache.safe_path("bls-projections.json")
    cache_file.unlink()
    r = await server.get_program_alignment("999001", "51.38", 2)
    assert r["data"]["openings_summary"] is None and r["data"]["occupations"]["rows"]
    assert any(n["field"] == "bls_projections" and "HIGHERED_MCPS_CONTACT" in n["reason"] for n in r["nulls"])
    assert r["data"]["institution_program"] is not None  # supply and outcomes still returned
    with pytest.raises(ToolError, match="HIGHERED_MCPS_CONTACT"):
        await server.get_occupation_outlook("29-1141")


async def test_second_call_uses_cache_and_stale_served_on_failure(upstream):
    await server.get_occupation_outlook("29-1141")
    n = len(upstream.requests)
    await server.get_occupation_outlook("25-1072")
    assert len(upstream.requests) == n
    p = cache.safe_path("bls-projections.json")
    blob = json.loads(p.read_text())
    blob["meta"]["retrieved_at"] = "2020-01-01T00:00:00+00:00"
    p.write_text(json.dumps(blob))
    upstream.bls_status = 503
    r = await server.get_occupation_outlook("29-1141")
    assert r["sources"][0]["served_stale_cache"] is True
    assert CONTACT not in json.dumps(r)
