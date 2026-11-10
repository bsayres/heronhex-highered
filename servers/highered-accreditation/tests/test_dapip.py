import io
import json
import zipfile
from datetime import date

import pytest

from highered_accreditation import cache
from highered_accreditation.sources import dapip

from .conftest import INJECTION, INST_COLS, PII, _csv, inst, make_zip


def parsed(**kw):
    return dapip.parse(make_zip(**kw))


def test_parse_counts_and_join():
    d = parsed()
    assert set(d["institutions"]) == {"999001", "111111", "222222", "300000"}
    assert d["institutions"]["111111"]["dapip_id"] == d["institutions"]["222222"]["dapip_id"] == "100500"
    assert d["counts"]["institutions_without_unitid"] == 1 and d["counts"]["rows_with_several_unitids"] == 1
    assert d["latest_action_date"] == "2026-10-29"  # taken from every action, including institutions we do not keep
    assert "999999" not in d["institutions"]  # an Additional Location row is never an institution
    assert "990001002" not in d["records"] and "990001002" not in d["actions"]  # branch rows are dropped
    assert d["institutions"]["300000"]["opeid"] is None  # malformed OPE id is not carried


def test_personal_fields_never_parsed_or_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    d = parsed()
    blob = json.dumps(d)
    for s in PII:
        assert s not in blob
    cache.write("dapip.json", d, "x", "https://ope.ed.gov/dapip/")
    assert not any(s in (tmp_path / "accreditation" / "dapip.json").read_text() for s in PII)


def test_text_is_cleaned_and_capped():
    d = parsed()
    assert "\x1b" not in d["institutions"]["300000"]["name"]
    longest = max(len(x) for x in d["strings"])
    assert longest <= dapip.JUSTIFICATION_OTHER_CAP
    assert all("\x00" not in x and "\x07" not in x for x in d["strings"])
    # Upstream text is kept as data and not interpreted.
    assert any(INJECTION in x for x in d["strings"])


@pytest.mark.parametrize("raw,expected", [
    ("1/29/2016 12:00:00 AM", "2016-01-29"), ("12/31/2023", "2023-12-31"), ("02/01/2023", "2023-02-01"),
    ("13/45/2020 12:00:00 AM", None), ("2/30/2020", None), ("1/1/1800", None), ("1/1/2999", None), ("", None), (None, None),
    ("2016-01-29", None), ("１/２９/２０１６", None), ("1/29/2016\n", "2016-01-29"),
])
def test_parse_date(raw, expected):
    assert dapip.parse_date(raw) == expected


@pytest.mark.parametrize("text,category", [
    ("Renewal of Accreditation", "routine"),
    ("Initial Accreditation", "routine"),
    ("Probation or Equivalent or a More Severe Status: Show Cause", "adverse"),
    ("Probation or Equivalent or More Severe Status: Monitoring", "adverse"),
    ("Warning or Equivalent-Factors Affecting Academic Quality", "adverse"),
    ("Loss of Accreditation or Preaccreditation: Voluntary Withdrawal", "loss"),
    ("Affirm Denial Following Appeal", "loss"),
    ("Removal of Approval of a Program", "loss"),
    ("Removal of Approval for Distance Education", "adverse"),
    ("Heightened Monitoring or Focused Review", "monitoring"),
    ("Removal of Show Cause Status", "resolved"),
    ("Accreditation Reaffirmed:  Warning Removed", "resolved"),
    ("Grant Substantive Change: Degree", "substantive_change"),
    ("Additional Location Closed", "closure"),
    ("Change in Agency recognition", "agency_recognition"),
    ("  renewal   of ACCREDITATION ", "routine"),
    ("Stay Denial Pending Appeal", "unclassified"),
    ("Brand New Action Wording", "unclassified"),
    ("", "unclassified"),
    (None, "unclassified"),
])
def test_categorize(text, category):
    assert dapip.categorize(text) == category


def test_every_category_has_a_note():
    assert {c for _, c in dapip.CATEGORY_RULES} | {"unclassified"} == set(dapip.CATEGORY_NOTES)


def test_current_is_computed_from_the_end_date_not_the_status_text():
    d = parsed()
    recs = {r["agency_name"]: r for r in dapip.accreditors(d, "999001", "all", date(2026, 10, 31))}
    neche = recs["New England Commission of Higher Education"]
    assert neche["current"] and neche["status_note"] is None
    adn = next(r for r in recs.values() if r["program"].startswith("Nursing"))
    assert adn["status_as_recorded"] == "Accredited" and adn["end_date"] == "2019-12-31" and not adn["current"] and adn["status_note"]
    # The same record is current on a day before it ended.
    early = next(r for r in dapip.accreditors(d, "999001", "all", date(2019, 6, 1)) if r["program"].startswith("Nursing"))
    assert early["current"]
    # Ending today counts as ended; a future end date is current and noted.
    assert not next(r for r in dapip.accreditors(d, "999001", "all", date(2019, 12, 31)) if r["program"].startswith("Nursing"))["current"]
    future = next(r for r in dapip.accreditors(d, "111111", "all", date(2026, 10, 31)) if r["agency_name"] == "Some Regional Commission")
    assert future["current"] and "future" in future["status_note"]
    denied = next(r for r in dapip.accreditors(d, "111111", "all", date(2026, 10, 31)) if r["agency_name"] == "Some Specialty Council")
    assert not denied["current"]


def test_impossible_review_date_becomes_null():
    r = next(x for x in dapip.accreditors(parsed(), "300000", "all", date(2026, 10, 31)) if x["agency_name"] == "Hostile Agency")
    assert r["review_date"] is None and r["status_as_recorded"] == "Preaccredited" and r["current"]


def test_scopes():
    d = parsed()
    today = date(2026, 10, 31)
    assert {r["scope"] for r in dapip.accreditors(d, "999001", "institutional", today)} == {"institutional"}
    assert {r["scope"] for r in dapip.accreditors(d, "999001", "programmatic", today)} == {"programmatic"}
    assert dapip.accreditors(d, "999001", "state", today) == []
    state = dapip.accreditors(d, "300000", "state", today)
    assert [r["agency_type"] for r in state] == ["state_agency"] and state[0]["scope"] == "programmatic"
    assert [a["agency_id"] for a in dapip.state_agencies(d)] == [71]


# ---- the downloaded zip is untrusted --------------------------------------------------------------

def test_not_a_zip_is_rejected():
    with pytest.raises(dapip.ParseError):
        dapip.parse(b"<html>Access denied</html>")


@pytest.mark.parametrize("extra", [{"../evil.csv": b"x"}, {"/etc/passwd": b"x"}, {"AccreditationRecords.csv.exe": b"x"}, {"sub/InstitutionCampus.csv": b"x"}])
def test_unexpected_or_path_traversal_members_are_rejected(extra):
    with pytest.raises(dapip.ParseError):
        dapip.parse(make_zip(extra=extra))


def test_missing_member_is_rejected():
    with pytest.raises(dapip.ParseError):
        dapip.parse(make_zip(drop="AccreditationActions.csv"))


@pytest.mark.filterwarnings("ignore:Duplicate name")
def test_duplicate_member_name_is_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in ("InstitutionCampus.csv", "InstitutionCampus.csv", "AccreditationRecords.csv", "AccreditationActions.csv"):
            z.writestr(name, b"x")
    with pytest.raises(dapip.ParseError):
        dapip.parse(buf.getvalue())


def test_zip_bomb_is_rejected_before_reading():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("InstitutionCampus.csv", b"0" * 20_000_000)
        z.writestr("AccreditationRecords.csv", b"x")
        z.writestr("AccreditationActions.csv", b"x")
    assert len(buf.getvalue()) < 100_000
    with pytest.raises(dapip.ParseError, match="large"):
        dapip.parse(buf.getvalue())


def test_oversized_member_is_rejected(monkeypatch):
    monkeypatch.setattr(dapip, "MAX_MEMBER_BYTES", 100)
    with pytest.raises(dapip.ParseError):
        dapip.parse(make_zip())


def test_read_is_bounded_even_if_declared_size_is_wrong(monkeypatch):
    with zipfile.ZipFile(io.BytesIO(make_zip())) as z:
        monkeypatch.setattr(dapip, "MAX_MEMBER_BYTES", 50)
        with pytest.raises(dapip.ParseError):
            dapip._rows(z, "InstitutionCampus.csv")


def test_changed_columns_are_rejected():
    cols = [c for c in INST_COLS if c != "IpedsUnitIds"]
    with pytest.raises(dapip.ParseError, match="layout"):
        dapip.parse(make_zip(inst_cols=cols))


def test_malformed_ids_in_rows_are_skipped_not_trusted():
    rows = [inst("99000", "999001", "Short Id"), inst("990001", "99900x ../../x 999001", "Ok", ope="09990100")]
    d = dapip.parse(make_zip(inst_rows=rows, rec_rows=[], act_rows=[]))
    assert list(d["institutions"]) == ["999001"] and d["counts"]["skipped_rows"] == 1


def test_text_helpers():
    assert dapip.clean_text("a\x00b\u0085c\n\td") == "a b c d"
    assert dapip.clean_text("   ") is None and dapip.clean_text(None) is None
    assert len(dapip.clean_text("x" * 1000, 50)) == 50
    assert _csv(["a"], [{"a": "1"}]).startswith(b"\xef\xbb\xbf")  # the real file has a BOM; the parser must cope


def test_location_rows_are_ignored_even_with_a_six_digit_id():
    rows = [inst("990001", "999001", "Test Community College A"), inst("555555", "555555", "A Site", kind="Site"),
            inst("666666", "666666", "An Additional Location", kind="Additional Location")]
    d = dapip.parse(make_zip(inst_rows=rows, rec_rows=[], act_rows=[]))
    assert list(d["institutions"]) == ["999001"]


def test_member_reads_ask_for_a_bounded_amount():
    asked = []

    class Member(io.BytesIO):
        def read(self, n=-1):
            asked.append(n)
            return super().read(n)

        def __enter__(self):
            return self

    class FakeZip:
        def open(self, name):
            return Member(b"DapipId,OpeId,IpedsUnitIds,LocationName,LocationType,UpdateDate\n")

    dapip._rows(FakeZip(), "InstitutionCampus.csv")
    assert asked == [dapip.MAX_MEMBER_BYTES + 1]


def test_review_date_note_only_when_current_review_date_is_over_five_years_old_with_no_later_action():
    d = parsed()
    neche = lambda today: next(r for r in dapip.accreditors(d, "999001", "all", today) if r["agency_name"].startswith("New England"))
    assert neche(date(2026, 10, 31))["review_date_note"] is None  # review date 2035 is in the future
    stale = neche(date(2041, 1, 1))  # review 2035-12-31 is now more than five years past; last action 2025
    assert stale["current"] and "more than five years past" in stale["review_date_note"] and "2035-12-31" in stale["review_date_note"]
    ended = next(r for r in dapip.accreditors(d, "999001", "all", date(2041, 1, 1)) if r["program"].startswith("Nursing"))
    assert not ended["current"] and ended["review_date_note"] is None  # an ended record needs no stale-date note


def test_action_window_bounds_what_the_history_can_say():
    d = parsed()
    w = dapip.action_window(d, "999001")
    assert (w["earliest_action_date"], w["latest_action_date"], w["actions_held"]) == ("2015-09-25", "2025-09-25", 8)
    assert "2015-09-25" in w["note"] and "ever lost or never lost" in w["note"]
    none = dapip.action_window(d, "111111")
    assert none["earliest_action_date"] is None and "no dated actions" in none["note"]
    assert dapip.action_window(d, "000000") is None
