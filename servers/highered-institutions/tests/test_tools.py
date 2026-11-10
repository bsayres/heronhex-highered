
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_institutions import cache
from highered_institutions import server as s


async def test_resolve_by_every_identifier(upstream):
    for q, kind in [("999001", "unitid_or_opeid6"), ("09990100", "opeid"), ("99-9000001", "ein"),
                    ("TESTCOLLEG1A", "uei"), ("https://www.college-a.example/about", "domain"),
                    ("Test Community College A", "name")]:
        d = (await s.resolve_institution(q))["data"]
        assert d["kind"] == kind and d["resolved"] is True, q
        assert d["candidates"][0]["unitid"] == "999001"
    # bare 6 digits that are also an OPEID6 prefix
    assert (await s.resolve_institution("099901"))["data"]["candidates"][0]["match_basis"] == "exact_opeid6"


async def test_never_guesses_on_ambiguity(upstream):
    d = (await s.resolve_institution("Columbia College"))["data"]
    assert d["resolved"] is False and len(d["candidates"]) == 4
    assert (await s.resolve_institution("Columbia College", state="MO"))["data"]["resolved"] is True
    # partial name is never promoted to a single answer
    assert (await s.resolve_institution("Harvard"))["data"]["resolved"] is False
    d = (await s.resolve_institution("000000"))["data"]
    assert d["resolved"] is False and d["candidates"] == []


async def test_one_to_many_opeid8(upstream):
    d = (await s.resolve_institution("01303900"))["data"]
    assert d["resolved"] is False
    assert {c["unitid"] for c in d["candidates"]} == {"139579", "475121"}
    assert all("One-to-many OPEID mapping." in c["notes"] for c in d["candidates"])


async def test_profile_without_key_uses_demo_key_in_header_and_says_so(upstream):
    r = await s.get_institution_profile("999001")
    d = r["data"]
    assert d["scorecard"] is not None
    sc = next(q for q in upstream.requests if q.url.host == "api.data.gov")
    assert sc.headers["x-api-key"] == "DEMO_KEY" and "DEMO_KEY" not in str(sc.url)
    assert any("DEMO_KEY" in w and "COLLEGE_SCORECARD_API_KEY" in w for w in r["warnings"])
    assert d["identifiers"]["ein"] == "999000001"
    assert d["latest_fall_enrollment"]["year"] == 2024  # 2025 enrollment not published in fixtures
    for k in ("source", "source_url", "as_of", "retrieved_at"):
        assert r[k]


async def test_profile_with_key_sends_header_not_url(upstream, monkeypatch):
    monkeypatch.setenv("COLLEGE_SCORECARD_API_KEY", "TESTKEY123")
    r = await s.get_institution_profile("999001")
    assert r["data"]["scorecard"]["avg_net_price"] == 12552
    sc = next(q for q in upstream.requests if q.url.host == "api.data.gov")
    assert sc.headers["x-api-key"] == "TESTKEY123" and "TESTKEY123" not in str(sc.url)
    assert "TESTKEY123" not in repr(r)


async def test_enrollment_trend_has_explicit_nulls(upstream):
    r = await s.get_enrollment_trend("999001")
    assert r["data"]["columns"] == ["year", "enrollment_fall"]
    assert r["data"]["rows"][-1] == [2024, 2044] and r["data"]["rows"][0][0] == 2015
    r = await s.get_enrollment_trend("999001", start_year=2024, end_year=2026)
    assert any(row[1] is None for row in r["data"]["rows"]) and r["nulls"]


async def test_compare_peers_is_deterministic_and_documented(upstream):
    a = await s.compare_peers("999001", n_peers=3)
    b = await s.compare_peers("999001", n_peers=3)
    assert a["data"] == b["data"]
    assert a["data"]["peer_rule"]["match"] == {"control": "public", "cc_basic_2025": 12} and a["data"]["peer_rule"]["scope"]["scope"] == "national"
    assert any("not a market or system benchmark" in w for w in a["warnings"])
    ids = [p["unitid"] for p in a["data"]["peers"]]
    assert "999001" not in ids and len(ids) == 3
    assert sum(1 for row in a["data"]["rows"] if row[4]) == 10  # target rows, one per year


async def test_search_filters(upstream):
    r = await s.search_institutions(state="MO", name_contains="columbia")
    assert [row[0] for row in r["data"]["rows"]] == ["177065"]
    assert (await s.search_institutions(control="private_nonprofit", state="MA"))["data"]["total_matches"] >= 1


async def test_financial_snapshot_public_gasb_and_private_fasb(upstream):
    r = await s.get_financial_snapshot("999001")
    d = r["data"]
    assert d["year"] == 2023 and d["reported_basis"].startswith("GASB") and d["net_position_field_used"] == "net_position_end"
    f = d["figures"]
    assert f["rev_total_current"] == 46181628.0 and f["net_position_or_net_assets_end"] == 61681116.0 and f["rev_capital_approps"] == 1787499.0
    assert f["revenues_minus_expenses"] == 741664.0 and f["revenue_components_sum_to_total"] is True  # computed from reported totals
    assert "history" not in d and any("single year" in w and "not a trend" in w for w in r["warnings"])
    r = await s.get_financial_snapshot("166027")
    d = r["data"]
    assert d["reported_basis"].startswith("FASB") and d["net_position_field_used"] == "equity_end"
    assert {n["field"] for n in r["nulls"]} >= {"longterm_debt", "rev_appropriations_state"} and all(n["reason"] for n in r["nulls"])
    assert any("not directly comparable" in w for w in r["warnings"])
    for k in ("source", "source_url", "as_of", "retrieved_at"):
        assert r[k]


async def test_financial_snapshot_history_shows_the_trend_and_never_nets_out_capital(upstream):
    r = await s.get_financial_snapshot("999001", years=3)
    h = r["data"]["history"]
    assert [row[0] for row in h["rows"]] == [2021, 2022, 2023] and h["columns"][4] == "revenues_minus_expenses"
    result = {row[0]: row[4] for row in h["rows"]}
    assert result[2023] == 741664.0 and result[2021] < 0 < result[2022]  # the surplus is not stable: a single year would mislead
    assert not any("single year" in w for w in r["warnings"])
    assert any("not netted out" in w for w in r["warnings"]) and not any("excluding" in k for k in r["data"]["figures"])
    assert r["as_of"] == "IPEDS finance surveys 2021-2023"
    upstream.finance["2022"].pop("999001")
    cache.safe_path("urban-finance-999001-2022.json").unlink()  # finance rows are cached for a day; drop it to see the changed upstream
    r = await s.get_financial_snapshot("999001", years=3)
    assert [row[0] for row in r["data"]["history"]["rows"]] == [2021, 2023] and any(n["field"] == "FY2022" for n in r["nulls"])


async def test_financial_snapshot_unknown_unitid_no_record_and_bad_years(upstream):
    with pytest.raises(ToolError):
        await s.get_financial_snapshot("999999")
    upstream.finance["2023"].pop("999001")
    r = await s.get_financial_snapshot("999001")
    assert r["data"]["figures"] is None and any(n["field"] == "FY2023" for n in r["nulls"])
    for bad in (0, 11):
        with pytest.raises(Exception):  # noqa: B017
            await s.mcp.call_tool("get_financial_snapshot", {"unitid": "999001", "years": bad})


async def test_compare_peers_same_system_and_same_state_relax_the_carnegie_class_and_say_so(upstream):
    r = await s.compare_peers("999001", n_peers=5, scope="same_system")
    rule = r["data"]["peer_rule"]
    assert [p["unitid"] for p in r["data"]["peers"]] == ["999004"]  # Test College D CC: same system, different Carnegie class (11 vs 12)
    assert rule["scope"] == {"scope": "same_system", "state": None, "system": "Massachusetts Community Colleges"}
    assert rule["carnegie_class_required"] is False and rule["match"] == {"control": "public", "institution_level": 2}
    assert any("Only 1 peers" in w for w in r["warnings"]) and not any("size-matched across the country" in w for w in r["warnings"])
    r = await s.compare_peers("999001", n_peers=5, scope="same_state")
    assert {p["state"] for p in r["data"]["peers"]} == {"MA"} and "999001" not in [p["unitid"] for p in r["data"]["peers"]]
    assert "166027" not in [p["unitid"] for p in r["data"]["peers"]]  # Harvard is MA but private


async def test_compare_peers_same_system_needs_a_system_and_bad_scope_is_rejected(upstream):
    with pytest.raises(ToolError, match="no system name"):
        await s.compare_peers("177065", scope="same_system")  # Columbia College (MO) has no system in the directory
    with pytest.raises(Exception):  # noqa: B017
        await s.mcp.call_tool("compare_peers", {"unitid": "999001", "scope": "regional"})


async def test_compare_institutions_side_by_side_and_flags_differences(upstream):
    r = await s.compare_institutions(["999001", "166027"], enrollment_years=3)
    rows = {x["unitid"]: x for x in r["data"]["institutions"]}
    assert rows["999001"]["name"] == "Test Community College A" and rows["166027"]["control"] != rows["999001"]["control"]
    assert rows["999001"]["finance"]["year"] == 2023 and rows["999001"]["finance"]["total_revenues"] is not None
    assert r["data"]["enrollment_window"] == [2022, 2024]
    assert [x[0] for x in rows["166027"]["enrollment"]["rows"]] == [2022, 2023, 2024]
    assert any("different control" in w for w in r["warnings"]) and any("different accounting bases" in w for w in r["warnings"])
    assert not any("rank" in str(k).lower() for k in rows["999001"])  # no ranking or scoring is done
    assert r["sources"] and r["retrieved_at"]


async def test_compare_institutions_leaves_out_unknown_ids_with_a_null_and_needs_two(upstream):
    r = await s.compare_institutions(["999001", "166027", "999999"])
    assert [x["unitid"] for x in r["data"]["institutions"]] == ["999001", "166027"]
    assert any(n["field"] == "999999" and n["kind"] == "not_found" for n in r["nulls"])
    with pytest.raises(ToolError, match="Fewer than two"):
        await s.compare_institutions(["999001", "999999"])
    with pytest.raises(ToolError, match="once"):
        await s.compare_institutions(["999001", "999001"])


async def test_compare_institutions_rejects_bad_input_without_a_request(upstream):
    for ids in (["999001"], ["999001"] * 6, ["999001", "12345"], ["999001", "166027x"], "999001,166027", []):
        with pytest.raises(ToolError):
            await s.mcp.call_tool("compare_institutions", {"unitids": ids})
    assert not upstream.requests


async def test_cbsa_is_returned_by_resolve_and_profile_and_null_outside_a_metro(upstream):
    r = await s.resolve_institution("Test Community College A")
    assert r["data"]["candidates"][0]["cbsa"] == "14460"
    p = await s.get_institution_profile("999001")
    assert p["data"]["identifiers"]["cbsa"] == "14460" and not [n for n in p["nulls"] if n["field"] == "identifiers.cbsa"]
    other = next(x for x in upstream.directory["results"] if x["unitid"] != 999001)
    q = await s.get_institution_profile(str(other["unitid"]))
    assert q["data"]["identifiers"]["cbsa"] is None
    n = next(n for n in q["nulls"] if n["field"] == "identifiers.cbsa")
    assert n["kind"] == "not_applicable" and "nonmetropolitan" in n["reason"]


def test_metro_code_only_accepts_real_five_digit_codes():
    from highered_institutions import crosswalk as cw

    assert [cw.metro_code(v) for v in (14460, "14460", 22140.0, -2, -1, 0, None, "x", 99999, 100000, 5)] == ["14460", "14460", "22140", None, None, None, None, None, "99999", None, None]


async def test_a_directory_cache_from_an_older_version_without_cbsa_is_fetched_again(upstream):
    from highered_institutions import cache

    await s.resolve_institution("Test Community College A")
    path = cache.safe_path("urban-directory-2025.json")
    blob = cache.read("urban-directory-2025.json")
    old_rows = [{k: v for k, v in r.items() if k not in ("cbsa", "county_fips")} for r in blob["data"]]
    cache.write("urban-directory-2025.json", old_rows, blob["meta"]["as_of"], blob["meta"]["source_url"])
    s.set_guard(s.guard())  # clear the in-process index
    before = len(upstream.requests)
    r = await s.resolve_institution("Test Community College A")
    assert r["data"]["candidates"][0]["cbsa"] == "14460" and len(upstream.requests) > before and path.exists()
