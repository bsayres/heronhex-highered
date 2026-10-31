import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_funding import server
from highered_funding.sources import sheeo, wiche

from .conftest import SHEEO_REPORT, WICHE_FILE


def test_sheeo_discovery_takes_newest_fy_on_the_right_host_only():
    page = (f'<a href="https://shef.sheeo.org/wp-content/uploads/2025/04/SHEEO_SHEF_FY24_Report_Data.xlsx">a</a>'
            f'<a href="https://shef.sheeo.org{SHEEO_REPORT}">b</a><a href="https://shef.sheeo.org/wp-content/uploads/2026/04/SHEEO_SHEF_FY25_Sector_Data.xlsx">c</a>'
            '<a href="https://evil.example.com/wp-content/uploads/2026/04/SHEEO_SHEF_FY99_Report_Data.xlsx">d</a>'
            '<a href="https://shef.sheeo.org/wp-content/uploads/../../x/SHEEO_SHEF_FY30_Sector_Data.xlsx">e</a>')
    files = sheeo.pick_files(page)
    assert files["Report"].endswith("FY25_Report_Data.xlsx") and "evil" not in files["Report"] and "FY30" not in files["Sector"]
    with pytest.raises(sheeo.ParseError):
        sheeo.pick_files("<a href='/nothing'>x</a>")


async def test_state_funding_table_citation_and_units(upstream):
    r = await server.get_state_funding("MA", start_fy=2024)
    d = r["data"]
    assert d["columns"][0] == "fy" and d["columns"][-2:] == ["two_year_state_and_local_support", "four_year_state_and_local_support"]
    assert [x[0] for x in d["rows"]] == [2024, 2025]
    assert d["rows"][1][-2:] == [7.0, 9.0] and d["rows"][0][-2:] == [None, None]  # sector data only where published
    assert r["citation"].startswith("State Higher Education Executive Officers Association") and "unadjusted" in d["units"]
    assert r["as_of"].startswith("SHEF FY2025")
    for k in ("source", "source_url", "as_of", "retrieved_at"):
        assert r[k]


async def test_missing_fiscal_year_is_a_null_not_zero(upstream):
    r = await server.get_state_funding("MA", start_fy=2022, end_fy=2024)
    assert {n["field"] for n in r["nulls"]} == {"FY2022", "FY2023"} and all(n["reason"] for n in r["nulls"])


async def test_state_without_data_and_bad_window(upstream):
    with pytest.raises(ToolError, match="not in the SHEEO"):
        await server.get_state_funding("WY")
    with pytest.raises(ToolError, match="must not be after"):
        await server.get_state_funding("MA", start_fy=2025, end_fy=2020)


async def test_projection_rows_license_and_basis(upstream):
    r = await server.get_enrollment_projection("MA", sector="public", start_class_year=2023, end_class_year=2024)
    assert r["data"]["rows"] == [[2023, 75494, "Reported/Actual"], [2024, 74846, "Projection"]]
    assert "CC BY-NC-SA 4.0" in r["license"] and r["citation"].startswith("Lane, P.")
    assert any("not" in w and "single institution" in w for w in r["warnings"])  # states what it is not
    assert r["as_of"] == "11th edition, December 2024"


async def test_projection_race_and_unknown_series(upstream):
    r = await server.get_enrollment_projection("MA", sector="public", race_ethnicity="hispanic")
    assert r["data"]["rows"] == [[2024, 9000, "Projection"]]
    r = await server.get_enrollment_projection("MA", sector="private")
    assert r["data"]["rows"] == [] and r["nulls"][0]["field"] == "graduates"
    r = await server.get_enrollment_projection("MA", sector="public", start_class_year=2090)
    assert r["data"]["rows"] == [] and "window" in r["nulls"][0]["reason"]


def test_wiche_discovery_and_parser_guards():
    assert wiche.pick_file(f'<a href="{WICHE_FILE}">x</a>').startswith("https://www.wiche.edu/wp-content/")
    with pytest.raises(wiche.ParseError):
        wiche.pick_file('<a href="https://evil.example.com/wp-content/uploads/2024/12/Knocking-at-the-College-Door-x-Projections-Dataset-1.xlsx">x</a>')
    with pytest.raises(wiche.ParseError):
        wiche.parse(b"PK\x03\x04garbage")


@pytest.mark.parametrize("name,args", [
    ("get_state_funding", {"state": "XX"}), ("get_state_funding", {"state": "Massachusetts"}), ("get_state_funding", {"state": "MA", "start_fy": 1500}),
    ("get_enrollment_projection", {"state": "MA", "sector": "all"}), ("get_enrollment_projection", {"state": "MA", "race_ethnicity": "x"}),
    ("get_enrollment_projection", {"state": "MA; DROP"}),
])
async def test_bad_state_inputs_rejected_before_network(upstream, name, args):
    try:
        res = await server.mcp.call_tool(name, args)
        failed = bool(getattr(res, "is_error", False))
    except Exception:  # noqa: BLE001
        failed = True
    assert failed and not upstream.requests
