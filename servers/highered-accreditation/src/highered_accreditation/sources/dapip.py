"""DAPIP: the Department of Education's Database of Accredited Postsecondary Institutions and Programs.

The site's own Download button returns one zip holding three CSVs. The zip is held in memory only:
its members must be exactly the three expected names, are size- and ratio-checked, and are read with a
bounded read. Nothing is extracted to disk or executed. Administrator names, emails, phone numbers and
street addresses in the institution file are dropped at parse time and never cached.
"""
import csv
import hashlib
import io
import re
import zipfile
from datetime import UTC, date, datetime

from .. import cache
from ..http import DAPIP_PAGE, DOWNLOAD_URL, Guard, UpstreamError

SOURCE = "U.S. Department of Education, Database of Accredited Postsecondary Institutions and Programs (DAPIP)"
CACHE_NAME = "dapip.json"
MAX_ZIP_BYTES = 15_000_000
MAX_MEMBER_BYTES = 80_000_000
MAX_TOTAL_BYTES = 200_000_000
MAX_RATIO = 60

INSTITUTIONS, RECORDS, ACTIONS = "InstitutionCampus.csv", "AccreditationRecords.csv", "AccreditationActions.csv"
REQUIRED = {
    INSTITUTIONS: {"DapipId", "OpeId", "IpedsUnitIds", "LocationName", "LocationType", "UpdateDate"},
    RECORDS: {"DapipId", "AgencyId", "AgencyName", "ProgramName", "SequentialId", "InitialDateFlag", "AccreditationDate",
              "AccreditationStatus", "ReviewDate", "AccreditationEndDate"},
    ACTIONS: {"DapipId", "AgencyId", "AgencyName", "ProgramName", "SequentialId", "ActionDescription", "ActionDate",
              "JustificationDescription", "JustificationOther", "EndDate"},
}

INSTITUTIONAL_PROGRAM = "Institutional Accreditation"
# State agencies that DAPIP carries (state boards of nursing, state education and career-technical boards).
# Fixed by agency id after reading the agency list in the file; every other agency is a private accrediting agency.
STATE_AGENCY_IDS = frozenset({20, 65, 67, 68, 70, 71, 73})
CURRENT_STATUSES = frozenset({"Accredited", "Preaccredited"})
JUSTIFICATION_OTHER_CAP = 400

DAPIP_ID_RE = re.compile(r"^[0-9]{6}\Z")
UNITID_RE = re.compile(r"^[0-9]{6}\Z")
OPEID_RE = re.compile(r"^[0-9]{8}\Z")
SMALL_INT_RE = re.compile(r"^[0-9]{1,4}\Z")
DATE_RE = re.compile(r"^([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})(?: .*)?\Z")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]+")

# This tool's grouping of the agency's own wording (first matching prefix wins; matched on lower-case text).
# Wording that matches no rule is reported as "unclassified" rather than guessed.
CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    ("loss of accreditation or preaccreditation", "loss"),
    ("removal of approval for", "adverse"),
    ("removal of approval", "loss"),
    ("affirm denial following appeal", "loss"),
    ("probation or equivalent", "adverse"),
    ("warning or equivalent", "adverse"),
    ("adverse action initiated", "adverse"),
    ("deny substantive change", "adverse"),
    ("heightened monitoring or focused review", "monitoring"),
    ("deferral of action", "monitoring"),
    ("removal of monitoring status", "resolved"),
    ("removal of show cause status", "resolved"),
    ("accreditation reaffirmed", "resolved"),
    ("accreditation reinstated", "resolved"),
    ("approval of program reinstated", "resolved"),
    ("renewal of accreditation", "routine"),
    ("initial accreditation", "routine"),
    ("approved for distance education", "routine"),
    ("approved for correspondence education", "routine"),
    ("grant substantive change", "substantive_change"),
    ("program name change", "substantive_change"),
    ("program merged into institutional accreditation", "substantive_change"),
    ("institution closed", "closure"),
    ("additional location closed", "closure"),
    ("voluntary withdrawal received", "closure"),
    ("change in agency recognition", "agency_recognition"),
    ("agency no longer recognized", "agency_recognition"),
)
CATEGORY_NOTES = {
    "loss": "accreditation or approval ended (loss, denial affirmed, or program approval removed)",
    "adverse": "probation, show cause, warning, adverse action initiated, or a denied change",
    "monitoring": "heightened monitoring, focused review, or a deferred decision",
    "resolved": "a monitoring or sanction status removed, or accreditation reaffirmed or reinstated",
    "routine": "renewal, initial accreditation, or approval of distance or correspondence education",
    "substantive_change": "a change granted to a program, degree, ownership or similar",
    "closure": "an institution or location closed, or a withdrawal was received",
    "agency_recognition": "a change to the accrediting agency's own recognition",
    "unclassified": "wording this tool does not have a rule for; read the action text",
}


class ParseError(UpstreamError):
    pass


def categorize(action: str | None) -> str:
    text = " ".join((action or "").lower().split())
    for prefix, category in CATEGORY_RULES:
        if text.startswith(prefix):
            return category
    return "unclassified"


def clean_text(v, cap: int = 300) -> str | None:
    s = " ".join(CONTROL_RE.sub(" ", v or "").split())
    return s[:cap] or None


def parse_date(v) -> str | None:
    m = DATE_RE.match((v or "").strip())
    if not m:
        return None
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        d = date(year, month, day)
    except ValueError:
        return None
    return d.isoformat() if 1900 <= year <= 2100 else None


class _Strings:
    """Interns repeated text so the cached JSON stays small."""

    def __init__(self):
        self.items: list[str] = []
        self._index: dict[str, int] = {}

    def add(self, value: str | None) -> int | None:
        if value is None:
            return None
        i = self._index.get(value)
        if i is None:
            i = self._index[value] = len(self.items)
            self.items.append(value)
        return i


def _rows(z: zipfile.ZipFile, name: str):
    with z.open(name) as f:
        raw = f.read(MAX_MEMBER_BYTES + 1)
    if len(raw) > MAX_MEMBER_BYTES:
        raise ParseError("A file inside the DAPIP download is unexpectedly large; refusing to parse it.")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig", "replace")))
    if not REQUIRED[name] <= set(reader.fieldnames or []):
        raise ParseError("A DAPIP file has an unexpected layout (columns changed).")
    return reader


def _check_zip(z: zipfile.ZipFile, size: int) -> None:
    infos = z.infolist()
    if sorted(i.filename for i in infos) != sorted(REQUIRED):
        raise ParseError("The DAPIP download does not contain exactly the expected files.")
    if any(i.flag_bits & 0x1 for i in infos):
        raise ParseError("The DAPIP download is encrypted; refusing to parse it.")
    total = sum(i.file_size for i in infos)
    if any(i.file_size > MAX_MEMBER_BYTES for i in infos) or total > MAX_TOTAL_BYTES or total > MAX_RATIO * max(size, 1):
        raise ParseError("The DAPIP download is unexpectedly large when unpacked; refusing to parse it.")


def parse(blob: bytes) -> dict:
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        raise ParseError("The DAPIP download is not a valid zip file.") from None
    with z:
        _check_zip(z, len(blob))
        strings, agencies = _Strings(), {}
        institutions: dict[str, dict] = {}
        counts = {"institution_rows": 0, "institutions_without_unitid": 0, "rows_with_several_unitids": 0, "skipped_rows": 0}

        for r in _rows(z, INSTITUTIONS):
            if r["LocationType"] != "Institution":
                continue
            counts["institution_rows"] += 1
            dapip_id = (r["DapipId"] or "").strip()
            units = [u for u in re.split(r"[\s,;]+", r["IpedsUnitIds"] or "") if u]
            if not DAPIP_ID_RE.match(dapip_id):
                counts["skipped_rows"] += 1
                continue
            if not units:
                counts["institutions_without_unitid"] += 1
                continue
            if len(units) > 1:
                counts["rows_with_several_unitids"] += 1
            opeid = (r["OpeId"] or "").strip()
            entry = {"dapip_id": dapip_id, "opeid": opeid if OPEID_RE.match(opeid) else None,
                     "name": clean_text(r["LocationName"]), "updated": parse_date(r["UpdateDate"])}
            for u in units:
                if UNITID_RE.match(u):
                    institutions.setdefault(u, entry)
        wanted = {e["dapip_id"] for e in institutions.values()}

        records: dict[str, list] = {}
        for r in _rows(z, RECORDS):
            dapip_id = (r["DapipId"] or "").strip()
            if dapip_id not in wanted:
                continue
            aid = (r["AgencyId"] or "").strip()
            if not SMALL_INT_RE.match(aid):
                counts["skipped_rows"] += 1
                continue
            agencies.setdefault(aid, clean_text(r["AgencyName"], 400))
            seq = (r["SequentialId"] or "").strip()
            records.setdefault(dapip_id, []).append([
                int(aid), strings.add(clean_text(r["ProgramName"])), int(seq) if SMALL_INT_RE.match(seq) else 0,
                strings.add(clean_text(r["InitialDateFlag"], 40)), parse_date(r["AccreditationDate"]),
                strings.add(clean_text(r["AccreditationStatus"], 80)), parse_date(r["ReviewDate"]), parse_date(r["AccreditationEndDate"]),
            ])

        actions: dict[str, list] = {}
        latest = None
        for r in _rows(z, ACTIONS):
            when = parse_date(r["ActionDate"])
            if when and (latest is None or when > latest):
                latest = when
            dapip_id = (r["DapipId"] or "").strip()
            if dapip_id not in wanted:
                continue
            aid = (r["AgencyId"] or "").strip()
            if not SMALL_INT_RE.match(aid):
                counts["skipped_rows"] += 1
                continue
            agencies.setdefault(aid, clean_text(r["AgencyName"], 400))
            seq = (r["SequentialId"] or "").strip()
            actions.setdefault(dapip_id, []).append([
                int(aid), strings.add(clean_text(r["ProgramName"])), int(seq) if SMALL_INT_RE.match(seq) else 0,
                strings.add(clean_text(r["ActionDescription"], 200)), when, strings.add(clean_text(r["JustificationDescription"], 200)),
                strings.add(clean_text(r["JustificationOther"], JUSTIFICATION_OTHER_CAP)), parse_date(r["EndDate"]),
            ])
        counts.update(institutions=len(institutions), records=sum(map(len, records.values())), actions=sum(map(len, actions.values())))
        return {"strings": strings.items, "agencies": agencies, "institutions": institutions,
                "records": records, "actions": actions, "latest_action_date": latest, "counts": counts}


# ---- fetch + cache ------------------------------------------------------------------------------

class Loaded:
    def __init__(self, data: dict, meta: dict, stale: bool):
        self.data, self.meta, self.stale = data, meta, stale


async def load(guard: Guard) -> Loaded:
    hit = cache.read(CACHE_NAME)
    if hit and cache.is_fresh(hit["meta"]):
        return Loaded(hit["data"], hit["meta"], False)
    try:
        raw = await guard.post_download(max_bytes=MAX_ZIP_BYTES)
        parsed = parse(raw)
    except UpstreamError:
        if hit:
            return Loaded(hit["data"], hit["meta"], True)
        raise
    meta = cache.write(CACHE_NAME, parsed, parsed["latest_action_date"] or "unknown", DAPIP_PAGE,
                       file_sha256=hashlib.sha256(raw).hexdigest(), file_bytes=len(raw), download_endpoint=DOWNLOAD_URL)
    return Loaded(parsed, meta, False)


# ---- lookups -------------------------------------------------------------------------------------

def _scope_ok(scope: str, program: str | None, agency_id: int) -> bool:
    state = agency_id in STATE_AGENCY_IDS
    institutional = program == INSTITUTIONAL_PROGRAM
    return (scope == "all" or (scope == "state" and state)
            or (scope == "institutional" and institutional) or (scope == "programmatic" and not institutional))


def _kind(program: str | None) -> str:
    return "institutional" if program == INSTITUTIONAL_PROGRAM else "programmatic"


def institution(data: dict, unitid: str) -> dict | None:
    return data["institutions"].get(unitid)


def state_agencies(data: dict) -> list[dict]:
    return [{"agency_id": i, "agency_name": data["agencies"].get(str(i))} for i in sorted(STATE_AGENCY_IDS) if str(i) in data["agencies"]]


def accreditors(data: dict, unitid: str, scope: str, today: date) -> list[dict]:
    inst = institution(data, unitid)
    if inst is None:
        return []
    s, out = data["strings"], []
    iso = today.isoformat()
    for aid, prog, seq, flag, first, status, review, end in data["records"].get(inst["dapip_id"], []):
        program = s[prog] if prog is not None else None
        if not _scope_ok(scope, program, aid):
            continue
        status_text = s[status] if status is not None else None
        ended = end is not None and end <= iso
        current = status_text in CURRENT_STATUSES and not ended
        note = None
        if ended and status_text in CURRENT_STATUSES:
            note = "DAPIP still shows this status, but the record has an end date that has passed; the accreditation is not current."
        elif end is not None and not ended:
            note = "The record has a scheduled end date in the future."
        out.append({
            "agency_id": aid, "agency_name": data["agencies"].get(str(aid)),
            "agency_type": "state_agency" if aid in STATE_AGENCY_IDS else "accrediting_agency",
            "scope": _kind(program), "program": program, "sequence": seq,
            "first_accredited": first, "first_accredited_flag": s[flag] if flag is not None else None,
            "status_as_recorded": status_text, "review_date": review, "end_date": end,
            "current": current, "status_note": note,
        })
    out.sort(key=lambda r: (r["scope"] != "institutional", not r["current"], r["program"] or "", r["agency_id"]))
    return out


def action_list(data: dict, unitid: str, scope: str, since_year: int | None) -> list[dict]:
    inst = institution(data, unitid)
    if inst is None:
        return []
    s, out = data["strings"], []
    for aid, prog, seq, action, when, just, other, end in data["actions"].get(inst["dapip_id"], []):
        program = s[prog] if prog is not None else None
        if not _scope_ok(scope, program, aid):
            continue
        if since_year is not None and (when is None or int(when[:4]) < since_year):
            continue
        text = s[action] if action is not None else None
        out.append({
            "date": when, "agency_id": aid, "agency_name": data["agencies"].get(str(aid)),
            "agency_type": "state_agency" if aid in STATE_AGENCY_IDS else "accrediting_agency",
            "scope": _kind(program), "program": program, "action": text, "category": categorize(text),
            "justification": s[just] if just is not None else None,
            "justification_detail": s[other] if other is not None else None, "end_date": end,
        })
    out.sort(key=lambda r: (r["date"] or "", r["agency_id"]), reverse=True)
    return out


def now_date() -> date:
    return datetime.now(UTC).date()
