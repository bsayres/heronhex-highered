"""SHEEO State Higher Education Finance (SHEF): state-level public funding of higher education."""
import asyncio
import hashlib
import re

from .. import cache
from ..http import Guard, UpstreamError
from ._xlsx import MAX_FILE_BYTES, ParseError, open_workbook

PAGE = "https://shef.sheeo.org/data-downloads/"
SOURCE = "SHEEO State Higher Education Finance (SHEF)"
CITATION = "State Higher Education Executive Officers Association. (2026). State Higher Education Finance: FY 2025. Boulder, CO."
FILE_RE = re.compile(r"^https://shef\.sheeo\.org/wp-content/uploads/[0-9]{4}/[0-9]{2}/SHEEO_SHEF_FY([0-9]{2})_(Report|Sector)_Data\.xlsx\Z")
TTL_DAYS = 90

REPORT_COLS = {
    "Education Appropriations": "education_appropriations",
    "Net Tuition and Fee Revenue": "net_tuition_and_fee_revenue",
    "Total Education Revenue": "total_education_revenue",
    "Student Share": "student_share_of_education_revenue",
    "Net FTE Enrollment": "net_fte_enrollment",
    "State Public Financial Aid": "state_public_financial_aid",
    "Total State and Local Support": "total_state_and_local_support",
    "State Tax Appropriations": "state_tax_appropriations",
    "Local Appropriations": "local_appropriations",
    "Total Federal Stimulus": "total_federal_stimulus",
    "HECA (Inflation) Adjustment": "heca_adjustment",
    "COLI (Cost of Living) Adjustment": "coli_adjustment",
    "EMI (Enrollment Mix) Adjustment": "emi_adjustment",
    "CPI (Inflation) Adjustment": "cpi_adjustment",
}
SECTOR_COLS = {
    "Two-Year State and Local Support": "two_year_state_and_local_support",
    "Four-Year State and Local Support": "four_year_state_and_local_support",
}


class Loaded:
    def __init__(self, data, meta: dict, stale: bool):
        self.data, self.meta, self.stale = data, meta, stale


def pick_files(page_html: str) -> dict[str, str]:
    """{'Report': url, 'Sector': url} for the newest fiscal year listed on the page."""
    best: dict[str, tuple[int, str]] = {}
    for href in re.findall(r'href="([^"]+)"', page_html):
        m = FILE_RE.match(href)
        if m and int(m.group(1)) >= best.get(m.group(2), (-1, ""))[0]:
            best[m.group(2)] = (int(m.group(1)), href)
    if set(best) != {"Report", "Sector"}:
        raise ParseError("Could not find the SHEEO data files on the page; its layout may have changed.")
    return {k: v[1] for k, v in best.items()}


def parse(data: bytes, sheet: str, cols: dict[str, str]) -> dict:
    wb = open_workbook(data)
    if sheet not in wb.sheetnames:
        raise ParseError("SHEEO workbook does not have the expected sheet.")
    rows = wb[sheet].iter_rows(values_only=True)
    header = list(next(rows, ()))
    if header[:2] != ["State", "FY"] or not set(cols) <= set(header):
        raise ParseError("SHEEO workbook does not have the expected columns.")
    pos = {name: header.index(name) for name in cols}
    out: dict[str, dict[str, dict]] = {}
    for r in rows:
        if not r or not r[0] or not isinstance(r[1], (int, float)):
            continue
        out.setdefault(str(r[0]), {})[str(int(r[1]))] = {
            cols[n]: (r[i] if isinstance(r[i], (int, float)) else None) for n, i in pos.items()}
    if not out:
        raise ParseError("SHEEO sheet had no data rows.")
    return out


async def load(guard: Guard) -> Loaded:
    name = "sheeo-shef.json"
    hit = cache.read(name)
    if hit and cache.is_fresh(hit["meta"], TTL_DAYS):
        return Loaded(hit["data"], hit["meta"], False)
    try:
        page, page_url = await guard.get_bytes(PAGE, max_bytes=3_000_000)
        files = pick_files(page.decode("utf-8", "replace"))
        rraw, rurl = await guard.get_bytes(files["Report"], max_bytes=MAX_FILE_BYTES)
        sraw, _ = await guard.get_bytes(files["Sector"], max_bytes=MAX_FILE_BYTES)
        report = await asyncio.to_thread(parse, rraw, "Report Data", REPORT_COLS)
        sector = await asyncio.to_thread(parse, sraw, "Sector Data", SECTOR_COLS)
    except UpstreamError:
        if hit:
            return Loaded(hit["data"], hit["meta"], True)
        raise
    latest = max(int(fy) for s in report.values() for fy in s)
    data = {"report": report, "sector": sector, "latest_fy": latest}
    published = re.search(r"/uploads/([0-9]{4})/([0-9]{2})/", rurl)
    stamp = f"{published.group(1)}-{published.group(2)}" if published else "unknown"
    meta = cache.write(name, data, f"SHEF FY{latest} (file published {stamp})", rurl,
                       file_sha256=hashlib.sha256(rraw).hexdigest(), sector_sha256=hashlib.sha256(sraw).hexdigest(), page_url=page_url)
    return Loaded(data, meta, False)
