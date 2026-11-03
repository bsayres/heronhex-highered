"""BLS Occupational Employment and Wage Statistics (OEWS): wages by state and by metropolitan area.

Two annual zip files from www.bls.gov are read in memory (never extracted to disk): the state workbook and the metropolitan-area
workbook. Only the exact workbook name inside each zip is read, only detailed occupations are kept, and a slim table is cached.
Cells BLS marks `*` (no wage estimate), `**` (no employment estimate) or `#` (at or above the top code) are kept as the marker.
"""
import io
import re
import zipfile

from ..http import Guard
from ._load import Loaded, load, sha256
from ._xlsx import ParseError, open_workbook

PAGE = "https://www.bls.gov/oes/tables.htm"
BASE = "https://www.bls.gov/oes/special-requests/"
SOURCE = "BLS Occupational Employment and Wage Statistics (OEWS)"
NOTICE = "BLS.gov cannot vouch for the data or analyses derived from these data after the data have been retrieved from BLS.gov."
LINK_RE = re.compile(r'href="(?:https://www\.bls\.gov)?/oes/special-requests/oesm([0-9]{2})(st|ma)\.zip"')  # this host only; the URL is rebuilt from the year, never taken from the page'
SOC_RE = re.compile(r"^[0-9]{2}-[0-9]{4}\Z")
AREA_RE = re.compile(r"^[0-9]{1,7}\Z")
MAX_ZIP = {"st": 15_000_000, "ma": 60_000_000}
MAX_UNPACKED = 120_000_000  # the whole archive, uncompressed
MAX_MEMBER = 60_000_000
MARKS = ("*", "**", "#")
# (cached field name, workbook column)
FIELDS = [("emp", "TOT_EMP"), ("emp_rse", "EMP_PRSE"), ("jobs_per_1000", "JOBS_1000"), ("loc_quotient", "LOC_QUOTIENT"),
          ("h_mean", "H_MEAN"), ("h_median", "H_MEDIAN"), ("a_mean", "A_MEAN"), ("mean_rse", "MEAN_PRSE"),
          ("a_p10", "A_PCT10"), ("a_p25", "A_PCT25"), ("a_median", "A_MEDIAN"), ("a_p75", "A_PCT75"), ("a_p90", "A_PCT90")]
TOP_RE = re.compile(r"\$([0-9]{2,4}(?:\.[0-9]{2})?) per hour or \$([0-9]{1,3}(?:,[0-9]{3})+) per year")
RELEASE_RE = re.compile(r"^((?:May|November) [0-9]{4}) OEWS", re.IGNORECASE)


def newest(page: str, kind: str) -> str:
    """Two-digit year of the newest `oesmYY{st|ma}.zip` linked on the BLS tables page."""
    years = sorted({int(y) for y, k in LINK_RE.findall(page) if k == kind})
    if not years:
        raise ParseError("The BLS tables page does not list the expected OEWS file.")
    return f"{years[-1]:02d}"


def member_names(kind: str, yy: str) -> list[str]:
    """The workbooks we read: states are one file; the `ma` archive holds the metropolitan file (MSA) and the nonmetropolitan file (BOS)."""
    if kind == "st":
        return [f"oesm{yy}st/state_M20{yy}_dl.xlsx"]
    return [f"oesm{yy}ma/MSA_M20{yy}_dl.xlsx", f"oesm{yy}ma/BOS_M20{yy}_dl.xlsx"]


def read_member(raw: bytes, name: str) -> bytes:
    """The one workbook we expect, read from the archive in memory by its exact name."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            if len(infos) > 20 or sum(i.file_size for i in infos) > MAX_UNPACKED:
                raise ParseError("The BLS archive is larger than the safety limit.")
            info = next((i for i in infos if i.filename == name), None)
            if info is None or info.file_size > MAX_MEMBER:
                raise ParseError("The BLS archive does not contain the expected workbook.")
            return z.read(info)
    except zipfile.BadZipFile:
        raise ParseError("Download is not a valid zip file.") from None


def _cell(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip() if v is not None else ""
    if s in MARKS:
        return s
    try:
        return float(s.replace(",", "")) if s else None
    except ValueError:
        return None


def _area(v, kind: str) -> str | None:
    s = str(int(v)) if isinstance(v, (int, float)) else str(v or "").strip()
    if not AREA_RE.match(s):
        return None
    if kind == "st":
        return str(int(s))  # state FIPS without a leading zero, as the model's state map writes it
    return s.zfill(5) if len(s) <= 5 else s.zfill(7)


def parse(xlsx: bytes, kind: str) -> dict:
    wb = open_workbook(xlsx)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    try:
        header = [str(h or "").strip() for h in next(rows)]
    except StopIteration:
        raise ParseError("The OEWS workbook is empty.") from None
    need = ["AREA", "AREA_TITLE", "AREA_TYPE", "PRIM_STATE", "OCC_CODE", "OCC_TITLE", "O_GROUP"] + [c for _, c in FIELDS]
    if any(c not in header for c in need):
        raise ParseError("The OEWS workbook does not have the expected columns.")
    ix = {c: header.index(c) for c in need}
    areas: dict[str, dict] = {}
    titles: dict[str, str] = {}
    for r in rows:
        if str(r[ix["O_GROUP"]] or "") != "detailed":
            continue
        soc = str(r[ix["OCC_CODE"]] or "").strip()
        code = _area(r[ix["AREA"]], kind)
        if not SOC_RE.match(soc) or code is None:
            continue
        a = areas.setdefault(code, {"title": str(r[ix["AREA_TITLE"]] or "").strip()[:120], "state": str(r[ix["PRIM_STATE"]] or "").strip()[:2],
                                    "type": str(r[ix["AREA_TYPE"]] or "").strip()[:1], "rows": {}})
        titles.setdefault(soc, str(r[ix["OCC_TITLE"]] or "").strip()[:160])
        a["rows"][soc] = [_cell(r[ix[c]]) for _, c in FIELDS]
    if not areas:
        raise ParseError("The OEWS workbook had no detailed occupation rows.")
    release, top = None, None
    if "Field Descriptions" in wb.sheetnames:
        text = [" ".join(str(c) for c in row if c is not None) for row in wb["Field Descriptions"].iter_rows(values_only=True)]
        m = next((RELEASE_RE.match(t.strip()) for t in text if RELEASE_RE.match(t.strip())), None)
        release = m.group(1) if m else None
        t = next((TOP_RE.search(x) for x in text if TOP_RE.search(x)), None)
        top = {"hourly": float(t.group(1)), "annual": int(t.group(2).replace(",", ""))} if t else None
    return {"release": release, "top_code": top, "columns": [n for n, _ in FIELDS], "occupations": titles, "areas": areas}


def merge(parts: list[dict]) -> dict:
    """One table from the workbooks of an archive (metropolitan and nonmetropolitan area codes do not overlap)."""
    out = dict(parts[0])
    out["areas"], out["occupations"] = dict(parts[0]["areas"]), dict(parts[0]["occupations"])
    for p in parts[1:]:
        out["areas"].update(p["areas"])
        for soc, title in p["occupations"].items():
            out["occupations"].setdefault(soc, title)
    return out


async def get(guard: Guard, kind: str) -> Loaded:
    """kind is `st` (states) or `ma` (metropolitan and nonmetropolitan areas)."""
    async def fetch():
        page, _ = await guard.get_bytes(PAGE, max_bytes=3_000_000)
        yy = newest(page.decode("utf-8", "replace"), kind)
        raw, url = await guard.get_bytes(f"{BASE}oesm{yy}{kind}.zip", max_bytes=MAX_ZIP[kind])
        parsed = merge([parse(read_member(raw, name), kind) for name in member_names(kind, yy)])
        return parsed, f"{parsed['release'] or 'OEWS'} estimates (file oesm{yy}{kind})", url, {"file_sha256": sha256(raw)}

    return await load("oews-state.json" if kind == "st" else "oews-metro.json", 180, fetch)


LAYOUT = [("emp", "employment", "estimate"), ("emp_rse", "employment", "relative_standard_error_pct"), ("jobs_per_1000", "employment", "jobs_per_1000_jobs_in_area"),
          ("loc_quotient", "employment", "location_quotient"), ("a_mean", "annual", "mean"), ("a_p10", "annual", "p10"), ("a_p25", "annual", "p25"),
          ("a_median", "annual", "median"), ("a_p75", "annual", "p75"), ("a_p90", "annual", "p90"), ("h_mean", "hourly", "mean"), ("h_median", "hourly", "median"),
          ("mean_rse", "mean_wage", "relative_standard_error_pct")]


def shape(row: list, columns: list[str], top: dict | None) -> tuple[dict, list[dict], list[str]]:
    """One cached row as nested values, with a null (and its kind) for every marker or blank, and the list of top-coded fields."""
    got = dict(zip(columns, row))
    out: dict[str, dict] = {"employment": {}, "annual": {}, "hourly": {}, "mean_wage": {}}
    nulls, floors = [], []
    for key, group, name in LAYOUT:
        v, path = got.get(key), f"{group}.{name}"
        if isinstance(v, (int, float)):
            out[group][name] = v
        elif v == "#":
            code = None if top is None else top["hourly" if group == "hourly" else "annual"]
            out[group][name] = code
            if code is None:
                nulls.append({"field": path, "kind": "suppressed", "reason": "BLS shows this wage as at or above its top code and the top code could not be read from the file."})
            else:
                floors.append(path)
        else:
            out[group][name] = None
            if v in ("*", "**"):
                what = "an employment estimate" if group == "employment" else "an estimate for this wage"
                nulls.append({"field": path, "kind": "suppressed", "reason": f"BLS did not publish {what} for this occupation and area ({v} in the file)."})
            else:
                nulls.append({"field": path, "kind": "not_reported", "reason": "BLS left this cell blank (OEWS does not release every field for every occupation, for example hourly wages for occupations paid by the year)."})
    return out, nulls, floors


def _stem(word: str) -> str:
    """A light, disclosed stem so "nursing", "nurse" and "nurses" all find "Registered Nurses" and "Nursing Assistants": drop a trailing
    "ing", then "s", then "e", while at least four letters remain."""
    for ending in ("ing", "s", "e"):
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            word = word[: -len(ending)]
    return word


def search_occupations(occupations: dict[str, str], keyword: str, limit: int) -> tuple[list[tuple[str, str]], int]:
    """Detailed occupations whose title contains every word of `keyword` (case-insensitive, light stemming). Returns (rows, total matches)."""
    words = [w for w in re.split(r"[^a-z0-9]+", keyword.lower()) if w]
    if not words:
        return [], 0
    stems = [_stem(w) for w in words]
    phrase = " ".join(words)
    hits = []
    for soc, title in occupations.items():
        t = " ".join(re.split(r"[^a-z0-9]+", title.lower())).strip()
        if all(st in t for st in stems):
            hits.append(((0 if phrase in t else 1, 0 if t.startswith(stems[0]) else 1, title.lower(), soc), (soc, title)))
    hits.sort(key=lambda h: h[0])
    return [h[1] for h in hits[:limit]], len(hits)
