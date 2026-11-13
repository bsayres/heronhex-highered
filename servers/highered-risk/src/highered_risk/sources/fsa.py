"""FSA public files: Heightened Cash Monitoring, financial responsibility composite scores, cohort default rates.

File locations are discovered from the pages' published link lists (never guessed), downloaded on demand,
parsed with read-only parsers, and cached as compact JSON with the source file's SHA-256.
Downloaded content is only ever parsed as spreadsheet data; nothing is executed or extracted to disk.
"""
import asyncio
import hashlib
import io
import re
import zipfile
from datetime import UTC, datetime

import openpyxl

from .. import cache
from ..http import Guard, UpstreamError

STUDENTAID = "https://studentaid.gov"
HCM_PAGE = f"{STUDENTAID}/data-center/school/hcm.json"
COMPOSITE_PAGE = f"{STUDENTAID}/data-center/school/composite-scores.json"
CDR_PAGE = "https://fsapartners.ed.gov/knowledge-center/topics/default-management/official-cohort-default-rates-schools"
FSAPARTNERS = "https://fsapartners.ed.gov"
MAX_FILE_BYTES = 25_000_000
MAX_UNZIPPED = 250_000_000
# Segments may not start with "." so ".." and hidden names can never match.
FILE_PATH_RE = re.compile(r"^/sites/default/files/(?:[A-Za-z0-9_-][A-Za-z0-9_.-]*/)*[A-Za-z0-9_-][A-Za-z0-9_.-]*\.xlsx?\Z")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

SRC_HCM = "FSA Data Center: Heightened Cash Monitoring list"
SRC_COMPOSITE = "FSA Data Center: Financial Responsibility Composite Scores"
SRC_CDR = "FSA: Official Cohort Default Rates for Schools"
TTL = {"hcm": 30, "composite": 90, "cdr": 90}


class ParseError(UpstreamError):
    pass


def _check_zip(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > 500 or sum(i.file_size for i in infos) > MAX_UNZIPPED:
                raise ParseError("Spreadsheet is unexpectedly large; refusing to parse it.")
    except zipfile.BadZipFile:
        raise ParseError("Downloaded file is not a valid .xlsx workbook.") from None


def _norm(v) -> str:
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower())


def _opeid8(v) -> str | None:
    s = str(int(v)) if isinstance(v, float) else str(v or "").strip()
    return s.zfill(8) if s.isdigit() and len(s) <= 8 else None


def _clean_text(v) -> str | None:
    s = re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""
    return s or None


# ---- discovery ---------------------------------------------------------------------------------

def pick_hcm(page_text: str) -> str:
    best, best_key = None, None
    for path in set(re.findall(r"/sites/default/files/[A-Za-z0-9_./-]+", page_text)):
        m = re.search(r"schools-on-hcm-?([a-z]+)-?([0-9]{4})\.xlsx$", path.lower())
        if m and m.group(1)[:3] in MONTHS and FILE_PATH_RE.match(path):
            key = (int(m.group(2)), MONTHS[m.group(1)[:3]])
            if best_key is None or key > best_key:
                best, best_key = path, key
    if not best:
        raise ParseError("No HCM list file link found on the FSA page (page layout may have changed).")
    return STUDENTAID + best


def pick_composite(page_text: str) -> str:
    best, best_end = None, -1
    for path in set(re.findall(r"/sites/default/files/[A-Za-z0-9_./-]+", page_text)):
        m = re.search(r"ay-?([0-9][0-9])-([0-9][0-9])-composite-scores\.xlsx?$", path.lower())
        if m and FILE_PATH_RE.match(path) and int(m.group(2)) > best_end:
            best, best_end = path, int(m.group(2))
    if not best:
        raise ParseError("No composite score file link found on the FSA page (page layout may have changed).")
    return STUDENTAID + best


def pick_cdr(html: str) -> str:
    for href, text in re.findall(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.DOTALL):
        if "official cdrs for the past three fiscal years" in re.sub(r"\s+", " ", text).lower():
            path = re.sub(r"\s+", "", href)
            if FILE_PATH_RE.match(path) and path.endswith(".xlsx"):
                return FSAPARTNERS + path
    raise ParseError("No official CDR file link found on the FSA page (page layout may have changed).")


# ---- parsers (bytes in, plain data out) ---------------------------------------------------------

def parse_hcm(data: bytes) -> dict:
    _check_zip(data)
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows, as_of = [], None
    for ws in wb.worksheets:
        title = ws.title.strip().lower()
        if not (title.startswith(("all hcm", "reimbursement"))):
            continue
        header, cols = None, {}
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0 and row and row[0]:
                m = re.search(r"as of ([0-9]{2})-([0-9]{2})-([0-9]{4})", str(row[0]))
                if m and title.startswith("all hcm"):
                    as_of = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
            if header is None:
                names = [_norm(c) for c in row]
                if "opeid" in names:
                    header, cols = i, {n: j for j, n in enumerate(names) if n}
                continue
            if not row or row[0] in (None, "") or str(row[0]).strip().lower() == "no data":
                continue
            get = lambda k, row=row, cols=cols: row[cols[k]] if k in cols and cols[k] < len(row) else None
            ope = _opeid8(get("opeid"))
            if ope:
                rows.append({
                    "opeid": ope, "name": _clean_text(get("institutionname")), "city": _clean_text(get("city")),
                    "state": _clean_text(get("state")), "institution_type": _clean_text(get("institutiontypedesc")),
                    "monitor_method": _clean_text(get("monitormethod") or get("stoppaymonitormethod")),
                    "reason": _clean_text(get("reasonondescription")),
                    "list": "reimbursement" if title.startswith("reimbursement") else "hcm",
                })
    if as_of is None:
        raise ParseError("HCM file has an unexpected layout (no 'All HCM' sheet or as-of date).")
    return {"as_of": as_of, "rows": rows}


MAX_COMPOSITE_ROWS = 100_000  # FSA scores a few thousand institutions; a declared sheet far larger than that is not the file we expect


def _composite_cells(data: bytes) -> list[list]:
    """The first sheet as plain rows, from the legacy .xls (xlrd) or the .xlsx (openpyxl) form of the file. Dates become ISO strings.
    In .xls a date is a float the parser can only recognize by column, so the fiscal-year-end column is converted after the header is found."""
    if data[:4] == b"PK\x03\x04":
        _check_zip(data)
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        rows = []
        for r in wb.worksheets[0].iter_rows(values_only=True):
            rows.append([v.date().isoformat() if isinstance(v, datetime) else v for v in r])
            if len(rows) > MAX_COMPOSITE_ROWS:
                raise ParseError("Composite score file has far more rows than expected; refusing to parse it.")
        return rows
    if data[:4] != b"\xd0\xcf\x11\xe0":
        raise ParseError("Composite score file is not a spreadsheet.")
    import xlrd

    try:
        wb = xlrd.open_workbook(file_contents=data, on_demand=True)
    except (xlrd.XLRDError, ValueError):
        raise ParseError("Could not read the composite score workbook.") from None
    ws = wb.sheet_by_index(0)
    if ws.nrows > MAX_COMPOSITE_ROWS:
        raise ParseError("Composite score file has far more rows than expected; refusing to parse it.")
    rows = [ws.row_values(i) for i in range(ws.nrows)]
    header = _composite_header(rows)
    fye_col = next((j for j, n in enumerate(_norm(c) for c in rows[header]) if "fiscalyearend" in n), None)
    if fye_col is not None:
        for r in rows[header + 1:]:
            if fye_col < len(r) and isinstance(r[fye_col], float) and r[fye_col]:
                r[fye_col] = xlrd.xldate_as_datetime(r[fye_col], wb.datemode).date().isoformat()
    return rows


def _composite_header(rows: list[list]) -> int:
    header = next((i for i in range(min(10, len(rows))) if any(_norm(c) == "opeid" for c in rows[i])), None)
    if header is None:
        raise ParseError("Composite score file has an unexpected layout.")
    return header


def parse_composite(data: bytes) -> dict:
    rows = _composite_cells(data)
    title = str(rows[0][0]) if rows and rows[0] and rows[0][0] is not None else ""
    period = re.search(r"Ending Between ([0-9/]+) and ([0-9/]+)", title)
    src_date = re.search(r"as of ([A-Za-z]+ [0-9]{1,2}, [0-9]{4})", title)
    header = _composite_header(rows)
    names = [_norm(c) for c in rows[header]]
    col = {n: j for j, n in enumerate(names)}
    score_col = next((j for j, n in enumerate(names) if n.startswith("compositescore")), None)
    fye_col = next((j for j, n in enumerate(names) if "fiscalyearend" in n), None)
    out = []
    for r in rows[header + 1:]:
        r = list(r) + [None] * (len(names) - len(r))
        ope = _opeid8(r[col["opeid"]])
        if not ope:
            continue
        fye = r[fye_col] if fye_col is not None else None
        score = r[score_col] if score_col is not None else None
        numeric = isinstance(score, (int, float)) and not isinstance(score, bool)
        out.append({
            "opeid": ope, "name": _clean_text(r[col["institutionname"]]), "state": _clean_text(r[col.get("state", 0)]),
            "institution_type": _clean_text(r[col["institutiontype"]]) if "institutiontype" in col else None,
            "fiscal_year_end": fye if isinstance(fye, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", fye) else None,
            "composite_score": float(score) if numeric else None,
            "composite_score_raw_text": None if numeric else _clean_text(score),
        })
    return {"period": f"{period.group(1)} to {period.group(2)}" if period else None,
            "data_source_as_of": src_date.group(1) if src_date else None, "rows": out}


def parse_cdr(data: bytes) -> dict:
    _check_zip(data)
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    title, header, rows = None, None, []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            title = str(row[0] or "")
            continue
        if header is None:
            names = [_norm(c) for c in row]
            if "schoolcode" in names:
                header = {n: j for j, n in enumerate(names) if n}
            continue
        if not row or row[0] in (None, ""):
            break  # the sheet's declared dimension can be huge; stop at the first blank row
        g = lambda k, row=row, header=header: row[header[k]] if k in header and header[k] < len(row) else None
        rates = []
        for n in ("1", "2", "3"):
            if g("year" + n) is not None:
                rates.append({"cohort_fy": _clean_text(g("year" + n)), "defaulted": g("num" + n), "in_repayment": g("denom" + n), "rate_percent": g("defaultrate" + n)})
        rows.append({"opeid6": str(row[0]).strip(), "name": _clean_text(g("name")), "city": _clean_text(g("city")), "state": _clean_text(g("state")), "rates": rates})
    m = re.search(r"FY\s*([0-9]{4})", title)
    if header is None or not m:
        raise ParseError("Default rate file has an unexpected layout.")
    return {"latest_cohort_fy": m.group(1), "rows": rows}


# ---- fetch + cache ------------------------------------------------------------------------------

class Loaded:
    def __init__(self, data: dict, meta: dict, stale: bool):
        self.data, self.meta, self.stale = data, meta, stale


async def _load(guard: Guard, kind: str, finder, parser) -> Loaded:
    name = f"fsa-{kind}.json"
    hit = cache.read(name)
    if hit and cache.is_fresh(hit["meta"], TTL[kind]):
        return Loaded(hit["data"], hit["meta"], False)
    try:
        if kind == "cdr":
            body, _ = await guard.get_bytes(CDR_PAGE, max_bytes=2_000_000)
            file_url = pick_cdr(body.decode("utf-8", "replace"))
        else:
            page, _ = await guard.get_json(HCM_PAGE if kind == "hcm" else COMPOSITE_PAGE, max_bytes=2_000_000)
            file_url = finder(_flatten(page))
        raw, public = await guard.get_bytes(file_url, max_bytes=MAX_FILE_BYTES)
        parsed = await asyncio.to_thread(parser, raw)  # spreadsheet parsing takes seconds; keep the event loop free for other calls
    except UpstreamError:
        if hit:
            return Loaded(hit["data"], hit["meta"], True)
        raise
    as_of = parsed.get("as_of") or parsed.get("period") or f"FY{parsed.get('latest_cohort_fy')} cohort"
    meta = cache.write(name, parsed, str(as_of), public, file_sha256=hashlib.sha256(raw).hexdigest(), file_bytes=len(raw))
    return Loaded(parsed, meta, False)


def _flatten(page) -> str:
    import json

    return json.dumps(page)


async def hcm(guard: Guard) -> Loaded:
    return await _load(guard, "hcm", pick_hcm, parse_hcm)


async def composite(guard: Guard) -> Loaded:
    return await _load(guard, "composite", pick_composite, parse_composite)


async def cdr(guard: Guard) -> Loaded:
    return await _load(guard, "cdr", None, parse_cdr)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
