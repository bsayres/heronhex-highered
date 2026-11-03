import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from highered_funding import server

from .conftest import PSU_UEI

PEOPLE = ("lovelace", "ada@", "grace", "hopper", "po@nsf", "7035551212", "Program Officer", "pi@psu", "piEmail", "coPDPI")


async def test_nsf_exact_uei_and_no_person_fields_ever(upstream):
    r = await server.search_grant_awards([PSU_UEI], sources=["nsf"], limit=30)
    nsf = r["data"]["nsf"]
    assert nsf["matched_by"] == "exact UEI" and nsf["total_matching"] == 30 and nsf["returned"] == 30  # two pages of 25 + 5
    assert len({a["id"] for a in nsf["awards"]}) == 30 and nsf["awards"][0]["uei"] == PSU_UEI
    assert nsf["awards"][0]["obligated_usd"] == 150000 and nsf["awards"][0]["url"].startswith("https://www.nsf.gov/awardsearch/")
    blob = json.dumps(r)
    assert not any(p in blob for p in PEOPLE) and "abstract" not in blob.lower()
    reqs = [q for q in upstream.requests if q.url.host == "api.nsf.gov"]
    assert all(q.url.params["ueiNumber"] == PSU_UEI and "awardeeName" not in q.url.params for q in reqs)


async def test_nsf_dates_become_api_format_and_bad_dates_are_rejected(upstream):
    await server.search_grant_awards([PSU_UEI], sources=["nsf"], awarded_from="2025-01-02", awarded_to="2025-12-31", limit=5)
    p = next(q for q in upstream.requests if q.url.host == "api.nsf.gov").url.params
    assert p["dateStart"] == "01/02/2025" and p["dateEnd"] == "12/31/2025"
    with pytest.raises(ToolError, match="valid calendar date"):
        await server.search_grant_awards([PSU_UEI], sources=["nsf"], awarded_from="2025-13-45")


async def test_nsf_truncation_ordering_and_bad_ids(upstream):
    upstream.nsf_total, upstream.nsf_bad_id = 99, True
    r = await server.search_grant_awards([PSU_UEI], sources=["nsf"], limit=10)
    assert r["data"]["nsf"]["total_matching"] == 99 and any("99 matching" in w for w in r["warnings"]) and any("not guaranteed" in w for w in r["warnings"])
    r = await server.search_grant_awards([PSU_UEI], sources=["nsf"], limit=50)
    assert any("award id" in w for w in r["warnings"]) and all("bad" not in a["id"] for a in r["data"]["nsf"]["awards"])


async def test_nih_keeps_only_uei_verified_rows_and_says_how(upstream):
    r = await server.search_grant_awards([PSU_UEI], sources=["nih"], institution_name="PENNSYLVANIA STATE UNIVERSITY", fiscal_year=2025)
    nih = r["data"]["nih"]
    assert "name query" in nih["matched_by"] and "exact UEI" in nih["matched_by"]
    assert [p["project_number"][-9:] for p in nih["projects"]] == ["000001-01", "000004-01"] and nih["verified_found"] == 2
    assert all(PSU_UEI in p["organization_ueis"] for p in nih["projects"])  # other org and intramural (no UEI) rows dropped
    post = next(q for q in upstream.requests if q.method == "POST")
    body = json.loads(post.content)
    assert body["criteria"] == {"org_names": ["PENNSYLVANIA STATE UNIVERSITY"], "fiscal_years": [2025]} and "org_ueis" not in post.content.decode()
    assert not any(p in json.dumps(r) for p in ("principal", "pi_name", "contact"))


async def test_nih_fail_open_and_incomplete_cases_are_reported(upstream):
    upstream.nih_rows = [r for r in upstream.nih_rows if PSU_UEI not in (r["organization"]["org_ueis"] or [])]  # nothing verifies
    r = await server.search_grant_awards([PSU_UEI], sources=["nih"], institution_name="PENNSYLVANIA STATE", fiscal_year=2025)
    assert r["data"]["nih"]["projects"] == [] and "No NIH projects" in r["nulls"][0]["reason"]
    upstream.nih_total = 2_983_713  # junk query that matched the whole database
    r = await server.search_grant_awards([PSU_UEI], sources=["nih"], institution_name="UNIVERSITY", fiscal_year=2025)
    assert any("may be incomplete" in w for w in r["warnings"])


async def test_nih_requires_a_name_but_nsf_still_answers(upstream):
    r = await server.search_grant_awards([PSU_UEI], limit=5)
    assert r["data"]["nih"] is None and r["data"]["nsf"]["returned"] == 5
    assert any(n["field"] == "nih" and "institution_name" in n["reason"] for n in r["nulls"])
    with pytest.raises(ToolError):
        await server.search_grant_awards([PSU_UEI], sources=["nih"])


async def test_opportunities_are_labeled_and_filtered(upstream):
    r = await server.search_funding_opportunities(keyword="community college", eligibility="public_ihe", agency="HHS-NIH11", rows=5)
    d = r["data"]
    assert d["total_matching"] == 317 and len(d["opportunities"]) == 1 and d["opportunities"][0]["url"].endswith("/358959")  # bad id dropped
    assert "opportunities, not awards" in r["source"] and "SECRET.JWT" not in json.dumps(r)
    body = json.loads(next(q for q in upstream.requests if q.method == "POST").content)
    assert body["eligibilities"] == "06" and body["agencies"] == "HHS-NIH11" and body["oppStatuses"] == "forecasted|posted"
    assert any("317 opportunities match" in w for w in r["warnings"])
    tools = await server.mcp.list_tools()
    assert all("Ignore previous" not in (t.description or "") for t in tools) and "untrusted" in r["notice"]


@pytest.mark.parametrize("name,args", [
    ("search_grant_awards", {"ueis": []}), ("search_grant_awards", {"ueis": ["npm2j7mscf61"]}), ("search_grant_awards", {"ueis": ["NPM2J7MSCF6"]}),
    ("search_grant_awards", {"ueis": [PSU_UEI] * 4}), ("search_grant_awards", {"ueis": [PSU_UEI + " OR 1=1"]}), ("search_grant_awards", {"ueis": ["NPM2J7MSCF６1"]}),
    ("search_grant_awards", {"ueis": [PSU_UEI], "limit": 51}), ("search_grant_awards", {"ueis": [PSU_UEI], "limit": 0}),
    ("search_grant_awards", {"ueis": [PSU_UEI], "sources": ["usaspending"]}), ("search_grant_awards", {"ueis": [PSU_UEI], "awarded_from": "01/02/2025"}),
    ("search_grant_awards", {"ueis": [PSU_UEI], "institution_name": "x" * 5000}), ("search_grant_awards", {"ueis": [PSU_UEI], "institution_name": '"}; {"criteria"'}),
    ("search_funding_opportunities", {"agency": "ed; drop"}), ("search_funding_opportunities", {"rows": 500}), ("search_funding_opportunities", {"eligibility": "everyone"}),
    ("search_funding_opportunities", {"keyword": "<script>"}), ("search_funding_opportunities", {"statuses": ["archived"]}),
])
async def test_bad_award_inputs_rejected_before_network(upstream, name, args):
    try:
        res = await server.mcp.call_tool(name, args)
        failed = bool(getattr(res, "is_error", False))
    except Exception:  # noqa: BLE001
        failed = True
    assert failed and not upstream.requests


async def test_nsf_first_page_skips_nothing(upstream):
    """NSF's `offset` counts records to skip. Sending 1 for the first page drops the first record (found live: a
    9-award institution returned 8 and a 1-award filter returned none)."""
    upstream.nsf_total = 1
    r = await server.search_grant_awards([PSU_UEI], sources=["nsf"], limit=25)
    nsf = r["data"]["nsf"]
    assert nsf["total_matching"] == 1 and nsf["returned"] == 1
    offsets = [q.url.params["offset"] for q in upstream.requests if q.url.host == "api.nsf.gov"]
    assert offsets[0] == "0"


async def test_opportunity_titles_are_decoded_to_plain_text_and_far_close_dates_are_noted(upstream):
    hit = dict(upstream.grants_hits[0], id="358960", title="George M. O&rsquo;Brien &ndash; Centers &lt;b&gt;", closeDate="10/27/2076")
    upstream.grants_hits = [hit]
    r = await server.search_funding_opportunities()
    t = r["data"]["opportunities"][0]["title"]
    assert t == "George M. O’Brien – Centers <b>"  # decoded text; the notice still says it is untrusted
    assert "untrusted" in r["notice"]
    assert any("more than three years away" in w for w in r["warnings"])


async def test_near_close_dates_get_no_far_date_note(upstream):
    upstream.grants_hits = [dict(upstream.grants_hits[0], closeDate="01/13/2027")]
    r = await server.search_funding_opportunities()
    assert not any("more than three years away" in w for w in r["warnings"])


async def test_tool_descriptions_state_the_filter_and_keyword_limits(upstream):
    d = next(t for t in await server.mcp.list_tools() if t.name == "search_funding_opportunities").description
    assert "no such code" in d and "incomplete" in d and "broad text match" in d


async def test_nsf_warning_says_limit_when_limit_is_the_cause_and_not_otherwise(upstream):
    upstream.nsf_total = 30
    r = await server.search_grant_awards([PSU_UEI], sources=["nsf"], limit=10)
    assert any("because of `limit`" in w for w in r["warnings"])
    full = await server.search_grant_awards([PSU_UEI], sources=["nsf"], limit=50)
    assert not any("matching awards" in w for w in full["warnings"])
    upstream.nsf_total, upstream.nsf_bad_id = 30, True  # one row per page has an unusable id, so fewer come back than the total
    odd = await server.search_grant_awards([PSU_UEI], sources=["nsf"], limit=50)
    assert any("Raising `limit` will not recover them" in w for w in odd["warnings"]) and any("dropped" in w for w in odd["warnings"])


async def test_nsf_total_matching_equals_returned_at_maximum_limit(upstream):
    """A permanent gap between the two means rows are being lost (the first-record bug was exactly that)."""
    for total in (1, 24, 25, 26, 49, 50):
        upstream.nsf_total = total
        n = (await server.search_grant_awards([PSU_UEI], sources=["nsf"], limit=50))["data"]["nsf"]
        assert n["total_matching"] == total == n["returned"] == len({a["id"] for a in n["awards"]})
