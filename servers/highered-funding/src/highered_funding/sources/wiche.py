"""WICHE Knocking at the College Door: projections of high school graduates (state, region, nation).

License: CC BY-NC-SA 4.0. Nothing is redistributed by this project; every response carries the license and citation.
"""
import asyncio
import hashlib
import re

from .. import cache
from ..http import Guard, UpstreamError
from ._xlsx import MAX_FILE_BYTES, ParseError, open_workbook

PAGE = "https://www.wiche.edu/knocking/data/"
BASE = "https://www.wiche.edu"
SOURCE = "WICHE Knocking at the College Door: Projections of High School Graduates"
CITATION = ("Lane, P., Falkenstern, C., & Bransberger, P. (2024). Knocking at the College Door: Projections of High School Graduates. "
            "Western Interstate Commission for Higher Education. https://www.wiche.edu/knocking")
LICENSE = "CC BY-NC-SA 4.0 (attribution, non-commercial, share-alike): https://creativecommons.org/licenses/by-nc-sa/4.0/"
FILE_RE = re.compile(r"^(?:https://www\.wiche\.edu)?(/wp-content/uploads/[0-9]{4}/[0-9]{2}/Knocking-at-the-College-Door-[A-Za-z0-9-]{1,60}-Projections-Dataset-[0-9-]{1,20}\.xlsx)\Z")
TTL_DAYS = 180
SECTORS = {"Public (total, any)": "public", "Private (total, any)": "private", "Grand Total (public+private)": "total"}
RACES = {"Total/any": "total", "American Indian/Alaska Native": "american_indian_alaska_native", "Asian": "asian",
         "Black or African American": "black", "Hispanic or Latinx": "hispanic", "White": "white",
         "Native Hawaiian or Other Pacific Islander": "native_hawaiian_pacific_islander",
         "Asian/Pacific Islander Combined": "asian_pacific_islander_combined", "Two or more races": "two_or_more"}
NEED = ["Stabbr", "ClassOf", "SchoolSector", "Grade", "RaceEthnicity", "Students", "ActualProjected"]


class Loaded:
    def __init__(self, data, meta: dict, stale: bool):
        self.data, self.meta, self.stale = data, meta, stale


def pick_file(page_html: str) -> str:
    found = [m.group(1) for h in re.findall(r'href="([^"]+)"', page_html) if (m := FILE_RE.match(h))]
    if not found:
        raise ParseError("Could not find the WICHE dataset on the page; its layout may have changed.")
    return BASE + max(found)


def parse(data: bytes) -> dict:
    wb = open_workbook(data)
    if "Data" not in wb.sheetnames:
        raise ParseError("WICHE workbook does not have the expected sheet.")
    rows = wb["Data"].iter_rows(values_only=True)
    header = list(next(rows, ()))
    if not set(NEED) <= set(header):
        raise ParseError("WICHE workbook does not have the expected columns.")
    ix = {n: header.index(n) for n in NEED}
    out: dict[str, dict] = {}
    for r in rows:
        if r[ix["Grade"]] != "High school graduates":
            continue
        sector, race = SECTORS.get(r[ix["SchoolSector"]]), RACES.get(r[ix["RaceEthnicity"]])
        m = re.fullmatch(r"Class of ([0-9]{4})", str(r[ix["ClassOf"]]))
        if not (sector and race and m and isinstance(r[ix["Students"]], (int, float)) and r[ix["Stabbr"]]):
            continue
        out.setdefault(str(r[ix["Stabbr"]]), {}).setdefault(sector, {}).setdefault(race, {})[m.group(1)] = [
            int(r[ix["Students"]]), str(r[ix["ActualProjected"]])]
    if not out:
        raise ParseError("WICHE sheet had no graduate rows.")
    return out


async def load(guard: Guard) -> Loaded:
    name = "wiche-knocking.json"
    hit = cache.read(name)
    if hit and cache.is_fresh(hit["meta"], TTL_DAYS):
        return Loaded(hit["data"], hit["meta"], False)
    try:
        page, _ = await guard.get_bytes(PAGE, max_bytes=3_000_000)
        url = pick_file(page.decode("utf-8", "replace"))
        raw, public = await guard.get_bytes(url, max_bytes=MAX_FILE_BYTES)
        parsed = await asyncio.to_thread(parse, raw)  # a 12 MB workbook; keep the event loop free for other calls
    except UpstreamError:
        if hit:
            return Loaded(hit["data"], hit["meta"], True)
        raise
    return Loaded(parsed, cache.write(name, parsed, "11th edition, December 2024", public, file_sha256=hashlib.sha256(raw).hexdigest()), False)
