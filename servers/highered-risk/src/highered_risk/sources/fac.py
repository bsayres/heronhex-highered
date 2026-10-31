"""Federal Audit Clearinghouse (api.fac.gov, a PostgREST API): Single Audit summaries and findings.

Only an explicit field list is requested. The `general` table also carries contact names, emails
and phone numbers for auditee and auditor staff; those are never requested. The `findings` table
holds structured flags only (the free-text finding narratives live in a different table that this
module does not query).
"""
import os
import re

from ..http import Guard, UpstreamError

BASE = "https://api.fac.gov"
KEY_VAR = "FAC_API_KEY"
SOURCE = "Federal Audit Clearinghouse (GSA), Single Audit database"
REPORT_URL = "https://app.fac.gov/dissemination/summary/{}"
REPORT_ID_RE = re.compile(r"^\d{4}-\d{2}-(?:GSAFAC|CENSUS)-\d{10}$")

MAX_FINDINGS = 500

GENERAL_FIELDS = [
    "report_id", "audit_year", "auditee_name", "auditee_ein", "auditee_uei", "fy_start_date", "fy_end_date",
    "fac_accepted_date", "audit_type", "type_audit_code", "gaap_results", "is_going_concern_included",
    "is_internal_control_deficiency_disclosed", "is_internal_control_material_weakness_disclosed",
    "is_material_noncompliance_disclosed", "is_low_risk_auditee", "dollar_threshold", "total_amount_expended",
    "oversight_agency", "cognizant_agency", "resubmission_status", "resubmission_version",
]
FINDING_FIELDS = [
    "report_id", "reference_number", "award_reference", "type_requirement", "is_material_weakness",
    "is_significant_deficiency", "is_questioned_costs", "is_modified_opinion", "is_other_findings",
    "is_other_matters", "is_repeat_finding", "prior_finding_ref_numbers",
]
AWARD_FIELDS = ["report_id", "award_reference", "federal_agency_prefix", "federal_award_extension",
                "federal_program_name", "amount_expended", "findings_count", "is_major"]

FINDING_FLAGS = ["is_material_weakness", "is_significant_deficiency", "is_questioned_costs",
                 "is_modified_opinion", "is_other_findings", "is_other_matters", "is_repeat_finding"]
AUDIT_FLAGS = ["is_going_concern_included", "is_internal_control_deficiency_disclosed",
               "is_internal_control_material_weakness_disclosed", "is_material_noncompliance_disclosed",
               "is_low_risk_auditee"]


def has_key() -> bool:
    return bool(os.environ.get(KEY_VAR))


def _flag(v) -> bool | None:
    return {"Y": True, "Yes": True, "N": False, "No": False}.get(v)


async def _get(guard: Guard, table: str, params: dict) -> tuple[list[dict], str]:
    key = os.environ.get(KEY_VAR)
    if not key:
        raise KeyError(KEY_VAR)
    data, url = await guard.get_json(f"{BASE}/{table}", params=params, headers={"X-Api-Key": key})
    if not isinstance(data, list):
        raise UpstreamError("api.fac.gov returned an unexpected response shape.")
    return data, url


async def fetch(guard: Guard, *, ein: str | None, uei: str | None, years: int) -> dict:
    """Latest `years` audit submissions for one auditee, with their findings. Exact EIN or UEI match."""
    key, value = ("auditee_uei", uei) if uei else ("auditee_ein", ein)
    general, url = await _get(guard, "general", {
        key: f"eq.{value}", "select": ",".join(GENERAL_FIELDS), "order": "audit_year.desc,fac_accepted_date.desc",
        "limit": str(years),
    })
    reports = [g for g in general if REPORT_ID_RE.match(str(g.get("report_id", "")))]
    dropped = len(general) - len(reports)
    ids = ",".join(g["report_id"] for g in reports)
    findings, awards = [], []
    truncated = False
    if reports:
        findings, _ = await _get(guard, "findings", {
            "report_id": f"in.({ids})", "select": ",".join(FINDING_FIELDS), "order": "report_id,reference_number",
            "limit": str(MAX_FINDINGS + 1),
        })
        if len(findings) > MAX_FINDINGS:
            findings, truncated = findings[:MAX_FINDINGS], True
        awards, _ = await _get(guard, "federal_awards", {
            "report_id": f"in.({ids})", "findings_count": "gt.0", "select": ",".join(AWARD_FIELDS), "limit": "500",
        })
    program = {(a["report_id"], a["award_reference"]): a for a in awards}

    audits = []
    for g in reports:
        fs = []
        for f in findings:
            if f.get("report_id") != g["report_id"]:
                continue
            a = program.get((f["report_id"], f.get("award_reference")))
            fs.append({
                "reference_number": f.get("reference_number"),
                "compliance_requirement_code": f.get("type_requirement"),
                "program": None if a is None else {
                    "aln": f"{a['federal_agency_prefix']}.{a['federal_award_extension']}", "name": a["federal_program_name"]},
                **{k.removeprefix("is_"): _flag(f.get(k)) for k in FINDING_FLAGS},
            })
        audits.append({
            "report_id": g["report_id"], "report_url": REPORT_URL.format(g["report_id"]),
            "audit_year": g.get("audit_year"), "auditee_name": g.get("auditee_name"),
            "fy_start": g.get("fy_start_date"), "fy_end": g.get("fy_end_date"), "fac_accepted": g.get("fac_accepted_date"),
            "audit_type": g.get("audit_type"), "gaap_opinion": g.get("gaap_results"),
            "total_federal_expended": g.get("total_amount_expended"), "oversight_agency": g.get("oversight_agency") or None,
            "resubmission_status": g.get("resubmission_status"), "resubmission_version": g.get("resubmission_version"),
            **{k.removeprefix("is_").removesuffix("_disclosed").removesuffix("_included"): _flag(g.get(k)) for k in AUDIT_FLAGS},
            "finding_count": len(fs), "findings": fs,
        })
    return {"audits": audits, "url": url, "truncated": truncated, "dropped_bad_ids": dropped, "matched_by": key}
