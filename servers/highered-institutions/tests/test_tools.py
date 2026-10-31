
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


async def test_profile_degrades_without_key_and_explains_nulls(upstream):
    r = await s.get_institution_profile("999001")
    d = r["data"]
    assert d["scorecard"] is None and d["form_990"] is None
    reasons = {n["field"]: n["reason"] for n in r["nulls"]}
    assert "COLLEGE_SCORECARD_API_KEY" in reasons["scorecard"]
    assert "Public institutions" in reasons["form_990"]
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


async def test_profile_990_for_private_nonprofit(upstream):
    r = await s.get_institution_profile("166027", include_990=True)
    f = r["data"]["form_990"]
    assert f["filings"][0]["totrevenue"] and "pdf_url" not in f["filings"][0]
    assert "chief_admin_name" not in repr(r)


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
    assert a["data"]["peer_rule"]["match"] == {"control": "public", "cc_basic_2025": 12}
    ids = [p["unitid"] for p in a["data"]["peers"]]
    assert "999001" not in ids and len(ids) == 3
    assert sum(1 for row in a["data"]["rows"] if row[4]) == 10  # target rows, one per year


async def test_search_filters(upstream):
    r = await s.search_institutions(state="MO", name_contains="columbia")
    assert [row[0] for row in r["data"]["rows"]] == ["177065"]
    assert (await s.search_institutions(control="private_nonprofit", state="MA"))["data"]["total_matches"] >= 1
