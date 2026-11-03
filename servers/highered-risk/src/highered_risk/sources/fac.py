"""Federal Audit Clearinghouse (api.fac.gov, a PostgREST API): Single Audit summaries and findings.

Only an explicit field list is requested. The `general` table also carries contact names, emails
and phone numbers for auditee and auditor staff; those are never requested. The `findings` table
holds structured flags only (the free-text finding narratives live in a different table that this
module does not query).
"""
import calendar
import os
import re
import unicodedata
from datetime import date, timedelta

from ..http import Guard, UpstreamError

BASE = "https://api.fac.gov"
KEY_VAR = "FAC_API_KEY"
SOURCE = "Federal Audit Clearinghouse (GSA), Single Audit database"
REPORT_URL = "https://app.fac.gov/dissemination/summary/{}"
REPORT_ID_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-(?:GSAFAC|CENSUS)-[0-9]{10}\Z")

MAX_FINDINGS = 500

GENERAL_FIELDS = [
    "report_id", "audit_year", "auditee_name", "auditee_ein", "auditee_uei", "fy_start_date", "fy_end_date",
    "fac_accepted_date", "submitted_date", "auditor_certified_date", "auditee_certified_date", "audit_type", "type_audit_code", "gaap_results", "is_going_concern_included",
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


# FAC API Data Dictionary (https://fac.gov/api/dictionary): type_requirement is one or more of these letters, alphabetical,
# no repeats. D and K are reserved; there is no "O".
REQUIREMENT_LABELS = {
    "A": "Activities allowed or unallowed", "B": "Allowable costs/cost principles", "C": "Cash management", "E": "Eligibility",
    "F": "Equipment and real property management", "G": "Matching, level of effort, earmarking",
    "H": "Period of performance (or availability) of Federal funds", "I": "Procurement and suspension and debarment",
    "J": "Program income", "L": "Reporting", "M": "Subrecipient monitoring", "N": "Special tests and provisions", "P": "Other",
}
DICTIONARY_URL = "https://fac.gov/api/dictionary"
MODIFIED_OPINION_NOTE = ("FAC definition: 'Y' if the auditor identified the finding as the basis for a modified opinion. FAC does not say here which "
                         "opinion; the report-level financial statement opinion is gaap_opinion. Read the report for details.")
RULE = ("2 CFR 200.512(a): the reporting package is due within 30 days after the auditee receives the auditor's report or nine months after the end "
        "of the audit period, whichever is earlier (next business day if it falls on a weekend or federal holiday); the cognizant or oversight "
        "agency may authorize an extension. FAC data does not show extensions or the date the auditor's report was received.")


def requirement_labels(code: str | None) -> list[str] | None:
    """Label each letter of a requirement code; None if the code is empty or has a letter FAC does not define."""
    if not code or not re.fullmatch(r"[A-Z]{1,15}", code):
        return None
    labels = [REQUIREMENT_LABELS.get(c) for c in code]
    return None if any(x is None for x in labels) else labels


def _date(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def nine_month_mark(fy_end: date) -> date:
    """Nine months after the end of the audit period (month-end stays month-end), rolled to Monday if it lands on a weekend.
    Federal holidays are not applied."""
    month = fy_end.month + 9
    year, month = fy_end.year + (month - 1) // 12, (month - 1) % 12 + 1
    last = calendar.monthrange(year, month)[1]
    day = last if fy_end.day == calendar.monthrange(fy_end.year, fy_end.month)[1] else min(fy_end.day, last)
    d = date(year, month, day)
    return d + timedelta(days=(7 - d.weekday()) % 7 if d.weekday() >= 5 else 0)


def filing_timeline(g: dict) -> dict:
    fy_end, filed = _date(g.get("fy_end_date")), _date(g.get("submitted_date")) or _date(g.get("fac_accepted_date"))
    mark = nine_month_mark(fy_end) if fy_end else None
    return {
        "fy_end": g.get("fy_end_date"), "auditor_certified": g.get("auditor_certified_date"), "auditee_certified": g.get("auditee_certified_date"),
        "submitted": g.get("submitted_date"), "fac_accepted": g.get("fac_accepted_date"),
        "months_from_fy_end_to_submission": round((filed - fy_end).days / 30.44, 1) if fy_end and filed else None,
        "nine_month_mark": mark.isoformat() if mark else None,
        "days_after_nine_month_mark": (filed - mark).days if mark and filed else None,
    }


DEMO_KEY = "DEMO_KEY"  # api.data.gov's public shared key; heavily rate limited, so only a fallback for first runs
DEMO_NOTE = (f"{KEY_VAR} is not set, so this call used api.data.gov's shared DEMO_KEY, which allows only about 10 requests before it is blocked. "
             "Get a free key at https://api.data.gov/signup and set it in the server environment for normal use.")


def api_key() -> str:
    return os.environ.get(KEY_VAR) or DEMO_KEY


def using_demo_key() -> bool:
    return not os.environ.get(KEY_VAR)


def _flag(v) -> bool | None:
    return {"Y": True, "Yes": True, "N": False, "No": False}.get(v)


async def _get(guard: Guard, table: str, params: dict) -> tuple[list[dict], str]:
    data, url = await guard.get_json(f"{BASE}/{table}", params=params, headers={"X-Api-Key": api_key()})
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
                "compliance_requirement_labels": requirement_labels(f.get("type_requirement")),
                "program": None if a is None else {
                    "aln": f"{a['federal_agency_prefix']}.{a['federal_award_extension']}", "name": a["federal_program_name"]},
                **{k.removeprefix("is_"): _flag(f.get(k)) for k in FINDING_FLAGS},
            })
        audits.append({
            "report_id": g["report_id"], "report_url": REPORT_URL.format(g["report_id"]),
            "audit_year": g.get("audit_year"), "auditee_name": g.get("auditee_name"),
            "auditee_ein": g.get("auditee_ein"), "auditee_uei": g.get("auditee_uei"),
            "fy_start": g.get("fy_start_date"), "fy_end": g.get("fy_end_date"), "fac_accepted": g.get("fac_accepted_date"),
            "filing_timeline": filing_timeline(g),
            "audit_type": g.get("audit_type"), "gaap_opinion": g.get("gaap_results"),
            "total_federal_expended": g.get("total_amount_expended"), "oversight_agency": g.get("oversight_agency") or None,
            "resubmission_status": g.get("resubmission_status"), "resubmission_version": g.get("resubmission_version"),
            **{k.removeprefix("is_").removesuffix("_disclosed").removesuffix("_included"): _flag(g.get(k)) for k in AUDIT_FLAGS},
            "finding_count": len(fs), "findings": fs,
        })
    return {"audits": audits, "url": url, "truncated": truncated, "dropped_bad_ids": dropped, "matched_by": key}


REF_RE = re.compile(r"^[0-9]{4}-[0-9]{3}\Z")
TEXT_CAP = 6000  # characters kept per narrative
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value) -> tuple[str | None, bool]:
    """Plain text from an upstream narrative: control and invisible formatting characters removed, blank runs collapsed, capped.
    Returns (text, truncated). The text is still untrusted; it is never put in markup."""
    if not isinstance(value, str) or not value.strip():
        return None, False
    t = "".join(c for c in value.replace("\r\n", "\n").replace("\r", "\n") if unicodedata.category(c) != "Cf")
    t = _CONTROL.sub("", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n[ \t]*(?:\n[ \t]*){2,}", "\n\n", t).strip()
    if len(t) > TEXT_CAP:
        return t[:TEXT_CAP].rstrip() + " [cut]", True
    return t, False


async def narratives(guard: Guard, report_id: str, ref: str | None, limit: int) -> dict:
    """The auditor's finding text and the auditee's planned corrective action for one report. Exact report id (and optional finding)."""
    if not REPORT_ID_RE.match(report_id) or (ref is not None and not REF_RE.match(ref)):
        raise UpstreamError("Invalid report id or finding reference.")
    general, url = await _get(guard, "general", {
        "report_id": f"eq.{report_id}", "select": "report_id,auditee_name,audit_year,fy_end_date,fac_accepted_date", "limit": "1"})
    base = {"report_id": f"eq.{report_id}", "order": "finding_ref_number", "limit": str(limit + 1)}
    if ref:
        base["finding_ref_number"] = f"eq.{ref}"
    texts, _ = await _get(guard, "findings_text", {**base, "select": "finding_ref_number,finding_text,contains_chart_or_table"})
    plans, _ = await _get(guard, "corrective_action_plans", {**base, "select": "finding_ref_number,planned_action,contains_chart_or_table"})
    return {"report": general[0] if general else None, "texts": texts, "plans": plans, "url": url}
