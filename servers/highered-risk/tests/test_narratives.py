import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_risk import server
from highered_risk.sources import fac

RID = "2024-06-GSAFAC-0000417646"


async def rejected(args):
    try:
        res = await server.mcp.call_tool("get_finding_text", args)
        return bool(getattr(res, "is_error", False))
    except Exception:  # noqa: BLE001
        return True


async def test_returns_the_auditor_text_and_the_auditee_plan_for_each_finding(upstream):
    r = await server.get_finding_text(RID)
    d = r["data"]
    assert d["auditee_name"] == "Test Community College A" and d["audit_year"] == "2024" and d["report_url"].endswith(RID)
    assert [f["reference_number"] for f in d["findings"]] == ["2024-003", "2024-004", "2024-005"]  # the other report's finding is not mixed in
    first = d["findings"][0]
    assert "did not complete verification" in first["finding_text"]["text"] and "second reviewer" in first["auditee_corrective_action"]["text"]
    for k in ("source", "source_url", "as_of", "retrieved_at"):
        assert r[k]
    assert "untrusted" in r["notice"]
    assert any("staff names" in w for w in r["warnings"])


async def test_one_finding_by_reference(upstream):
    r = await server.get_finding_text(RID, reference_number="2024-003")
    assert [f["reference_number"] for f in r["data"]["findings"]] == ["2024-003"]
    q = [x for x in upstream.requests if x.url.path == "/findings_text"][-1]
    assert q.url.params["finding_ref_number"] == "eq.2024-003" and q.url.params["report_id"] == f"eq.{RID}"


async def test_text_is_cleaned_capped_and_stays_data(upstream):
    r = await server.get_finding_text(RID, reference_number="2024-004")
    f = r["data"]["findings"][0]
    t = f["finding_text"]
    assert t["truncated"] is True and len(t["text"]) <= fac.TEXT_CAP + 10 and t["text"].endswith("[cut]")
    assert "\x00" not in t["text"] and "\x07" not in t["text"] and "\u202e" not in t["text"] and "\u200b" not in t["text"]
    assert "Ignore previous instructions" in t["text"]  # returned as data, in a field, never in a description or instruction
    tools = await server.mcp.list_tools()
    assert all("Ignore previous" not in (x.description or "") for x in tools)
    assert any("cut at" in w for w in r["warnings"])


def test_whitespace_is_tidied_without_losing_words():
    t, cut = fac.clean_text("A:\t\tone   two\r\n\n\n\n\nB: three")
    assert t == "A: one two\n\nB: three" and cut is False
    assert fac.clean_text("   ") == (None, False) and fac.clean_text(None) == (None, False) and fac.clean_text(5) == (None, False)


async def test_missing_plan_and_chart_flag_are_reported(upstream):
    r = await server.get_finding_text(RID)
    by = {f["reference_number"]: f for f in r["data"]["findings"]}
    assert by["2024-004"]["auditee_corrective_action"] is None  # an empty plan is a gap, not an empty string
    assert any(n["field"] == "corrective_action[2024-004]" and n["kind"] == "not_found" for n in r["nulls"])
    assert by["2024-005"]["finding_text"]["contains_chart_or_table"] is True and any("chart or table" in w for w in r["warnings"])


async def test_limit_and_more_findings_warning(upstream):
    r = await server.get_finding_text(RID, limit=2)
    assert r["data"]["returned"] == 2 and any("More findings" in w for w in r["warnings"])


async def test_unknown_report_and_empty_result(upstream):
    with pytest.raises(ToolError, match="No FAC report"):
        await server.get_finding_text("2024-06-GSAFAC-0000999999")
    r = await server.get_finding_text("2023-06-GSAFAC-0000043760", reference_number="2023-009")
    assert r["data"]["findings"] == [] and r["nulls"][0]["kind"] == "not_found"


@pytest.mark.parametrize("args", [
    {"report_id": ""}, {"report_id": RID + "&select=*"}, {"report_id": RID.lower()}, {"report_id": "2024-06-OTHER-0000417646"},
    {"report_id": RID + " "}, {"report_id": RID, "reference_number": "2024-3"}, {"report_id": RID, "reference_number": "2024-003 OR 1=1"},
    {"report_id": RID, "reference_number": "2024-００３"}, {"report_id": RID, "limit": 0}, {"report_id": RID, "limit": 11},
    {"report_id": "x" * 5000},
])
async def test_bad_inputs_are_rejected_before_any_request(upstream, args):
    assert await rejected(args) and not upstream.requests


async def test_only_listed_fields_are_requested_and_the_key_is_a_header(upstream):
    await server.get_finding_text(RID)
    reqs = [x for x in upstream.requests if x.url.host == "api.fac.gov"]
    sel = {x.url.path: x.url.params["select"] for x in reqs}
    assert sel["/findings_text"] == "finding_ref_number,finding_text,contains_chart_or_table"
    assert sel["/corrective_action_plans"] == "finding_ref_number,planned_action,contains_chart_or_table"
    assert "email" not in json.dumps(sel).lower() and all("apikey" not in str(x.url).lower() and "TESTFACKEY" not in str(x.url) for x in reqs)
    assert all(x.headers["x-api-key"] == "TESTFACKEY123" for x in reqs)


async def test_there_is_no_search_by_name_or_text(upstream):
    """The tool has no name or text argument; one that is passed anyway changes nothing about what is requested."""
    props = next(t for t in await server.mcp.list_tools() if t.name == "get_finding_text").input_schema["properties"]
    assert set(props) == {"report_id", "reference_number", "limit"}
    await server.mcp.call_tool("get_finding_text", {"report_id": RID, "name": "Jane Doe", "text": "staff"})
    sent = " ".join(str(x.url) for x in upstream.requests)
    assert "Jane" not in sent and "staff" not in sent
