"""IPEDS fall enrollment, part D (retention) straight from NCES's complete data files.

`https://nces.ed.gov/ipeds/datacenter/data/EF{year}D.zip` holds the retention rates, the cohorts they are computed on and the
student-to-faculty ratio. Read in memory by exact member name, kept as a slim table per year, never extracted to disk.
"""
import csv
import io
import re
import zipfile
from datetime import UTC, datetime

from .. import cache
from ..http import BULK_TIMEOUT, Guard, NotFound, UpstreamError

BASE = "https://nces.ed.gov/ipeds/datacenter/data/"
SOURCE = "IPEDS Fall Enrollment, retention (NCES complete data files)"
MAX_ZIP = 3_000_000
MAX_MEMBER = 8_000_000
MAX_UNPACKED = 20_000_000
MEMBER_RE = re.compile(r"^ef([0-9]{4})d(_rv)?\.csv\Z")
UNITID_RE = re.compile(r"^[0-9]{6}\Z")
TTL_DAYS = 90
CODES = {"A": "Not applicable", "B": "Institution left item blank", "C": "Analyst corrected reported value", "D": "Do not know",
         "G": "Data generated from other data values", "H": "Value not derived - data not usable", "J": "Logical imputation", "K": "Ratio adjustment",
         "L": "Imputed using the Group Median procedure", "N": "Imputed using Nearest Neighbor procedure", "P": "Imputed using Carry Forward procedure",
         "R": "Reported", "Z": "Implied zero"}
# (kept field, rate-like columns): rate, retained, adjusted cohort; the flag column is X + the rate column
FT = ("RET_PCF", "RET_NMF", "RRFTCTA")
PT = ("RET_PCP", "RET_NMP", "RRPTCTA")
COLUMNS = ["ft_rate_pct", "ft_retained", "ft_cohort", "ft_flag", "pt_rate_pct", "pt_retained", "pt_cohort", "pt_flag", "student_faculty_ratio", "ratio_flag"]
NEEDED = ["UNITID", *FT, *PT, "XRET_PCF", "XRET_PCP"]


class ParseError(UpstreamError):
    pass


def _num(v) -> float | None:
    s = str(v or "").strip()
    try:
        n = float(s)
    except ValueError:
        return None
    return int(n) if n == int(n) else n


def _flag(v) -> str | None:
    s = str(v or "").strip().upper()
    return s[:1] if s else None


def read_member(raw: bytes, year: int) -> bytes:
    """The data file for the year, by exact name; the revised `_rv` file wins when both are present."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            if len(infos) > 10 or sum(i.file_size for i in infos) > MAX_UNPACKED:
                raise ParseError("The IPEDS archive is larger than the safety limit.")
            hits = {}
            for i in infos:
                m = MEMBER_RE.match(i.filename)
                if m and int(m.group(1)) == year:
                    hits[bool(m.group(2))] = i
            info = hits.get(True) or hits.get(False)
            if info is None or info.file_size > MAX_MEMBER:
                raise ParseError("The IPEDS archive does not contain the expected data file.")
            return z.read(info)
    except zipfile.BadZipFile:
        raise ParseError("Download is not a valid zip file.") from None


def parse(csv_bytes: bytes) -> dict:
    text = csv_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip().upper() for h in next(reader)]
    except StopIteration:
        raise ParseError("The IPEDS file is empty.") from None
    if any(c not in header for c in NEEDED):
        raise ParseError("The IPEDS file does not have the expected columns.")
    ix = {c: header.index(c) for c in header}
    rows: dict[str, list] = {}

    def cell(r: list, c: str):
        return r[ix[c]] if c in ix else None

    for r in reader:
        if len(r) < len(header) or not UNITID_RE.match(r[ix["UNITID"]].strip()):
            continue
        rows[r[ix["UNITID"]].strip()] = [
            _num(cell(r, FT[0])), _num(cell(r, FT[1])), _num(cell(r, FT[2])), _flag(cell(r, "XRET_PCF")),
            _num(cell(r, PT[0])), _num(cell(r, PT[1])), _num(cell(r, PT[2])), _flag(cell(r, "XRET_PCP")),
            _num(cell(r, "STUFACR")), _flag(cell(r, "XSTUFACR")),
        ]
    if not rows:
        raise ParseError("The IPEDS file had no institution rows.")
    return {"columns": COLUMNS, "rows": rows}


class Loaded:
    def __init__(self, data, meta: dict, stale: bool):
        self.data, self.meta, self.stale = data, meta, stale


async def _cached(name: str, ttl_days: int, fetch) -> Loaded:
    hit = cache.read(name)
    if hit and cache.is_fresh(hit["meta"], ttl_days):
        return Loaded(hit["data"], hit["meta"], False)
    try:
        data, as_of, url = await fetch()
    except UpstreamError:
        if hit:
            return Loaded(hit["data"], hit["meta"], True)
        raise
    return Loaded(data, cache.write(name, data, as_of, url), False)


async def year_table(guard: Guard, year: int) -> Loaded:
    """Retention table for one fall collection. NotFound means NCES has not published that year."""
    if not 1990 <= year <= 2100:
        raise UpstreamError("Invalid year.")

    async def fetch():
        raw, url = await guard.get_bytes(f"{BASE}EF{year}D.zip", max_bytes=MAX_ZIP, timeout=BULK_TIMEOUT)
        return parse(read_member(raw, year)), f"IPEDS fall {year} collection (EF{year}D)", url

    return await _cached(f"ipeds-ef{year}d.json", TTL_DAYS, fetch)


async def latest_year(guard: Guard) -> int:
    """Newest fall collection NCES has published: tries this year downward (the newest file is often not out yet)."""
    async def fetch():
        this = datetime.now(UTC).year
        for y in range(this, this - 4, -1):
            try:
                await year_table(guard, y)
            except NotFound:
                continue
            return {"year": y}, f"newest EF D file found: {y}", f"{BASE}EF{y}D.zip"
        raise UpstreamError("Could not find a published IPEDS retention file.")

    return (await _cached("ipeds-latest-ef-year.json", 30, fetch)).data["year"]

