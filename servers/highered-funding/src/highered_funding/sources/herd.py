"""NSF NCSES Higher Education R&D (HERD) Survey: per-year public-use microdata zips (long-format CSV).

Only total R&D expenditures by source of funds (questionnaire 01.a-01.g) are kept. Archives are read in
memory, only the one expected CSV member is read, and its decompressed size is capped while streaming.
"""
import csv
import hashlib
import io
import re
import zipfile

from .. import cache
from ..http import Guard, UpstreamError

PAGE = "https://ncses.nsf.gov/explore-data/microdata/higher-education-research-development"
BASE = "https://ncses.nsf.gov"
SOURCE = "NSF NCSES Higher Education Research and Development (HERD) Survey"
FILE_RE = re.compile(r"^/[0-9]{1,5}/assets/0/files/higher_education_r_and_d_([0-9]{4})(_short)?\.zip$")
MAX_ZIP_BYTES = 25_000_000
MAX_CSV_BYTES = 120_000_000
TTL_DAYS = 90

LINES = {"01.a": "federal", "01.b": "state_local", "01.c": "business", "01.d": "nonprofit", "01.e": "institution",
         "01.f": "other", "01.g": "total"}
UNITID_RE = re.compile(r"^[0-9]{6}$")


class ParseError(UpstreamError):
    pass


class Loaded:
    def __init__(self, data, meta: dict, stale: bool):
        self.data, self.meta, self.stale = data, meta, stale


def pick_files(page_html: str) -> dict[int, dict[str, str]]:
    """{year: {'standard': path, 'short': path?}} from the microdata page's own links."""
    out: dict[int, dict[str, str]] = {}
    for href in re.findall(r'href="([^"]+)"', page_html):
        m = FILE_RE.match(href)
        if m:
            out.setdefault(int(m.group(1)), {})["short" if m.group(2) else "standard"] = href
    if not out:
        raise ParseError("Could not find HERD data files on the NCSES page; its layout may have changed.")
    return out


def _lines(f, limit: int):
    total = 0
    for raw in io.BufferedReader(f):
        total += len(raw)
        if total > limit:
            raise ParseError("HERD file exceeds the decompressed size limit.")
        yield raw.decode("utf-8", "replace")


def parse_zip(data: bytes, year: int, form: str) -> dict:
    member = f"{'herd' if form == 'standard' else 'short'}{year}.csv"
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        infos = {i.filename: i for i in z.infolist()}
        if member not in infos:
            raise ParseError("HERD archive does not contain the expected file.")
        if infos[member].file_size > MAX_CSV_BYTES:
            raise ParseError("HERD file exceeds the decompressed size limit.")
        with z.open(member) as f:
            reader = csv.DictReader(_lines(f, MAX_CSV_BYTES))
            need = {"inst_id", "ipeds_unitid", "inst_name_long", "inst_city", "inst_state_code", "questionnaire_no", "data", "status"}
            if not need <= set(reader.fieldnames or []):
                raise ParseError("HERD file does not have the expected columns.")
            insts: dict[str, dict] = {}
            for r in reader:
                key = LINES.get(r["questionnaire_no"])
                if key is None:
                    continue
                rec = insts.setdefault(r["inst_id"], {
                    "unitid": r["ipeds_unitid"] if UNITID_RE.match(r["ipeds_unitid"] or "") else None,
                    "name": r["inst_name_long"], "city": r["inst_city"], "state": r["inst_state_code"],
                    "form": form, "usd": {}, "status": [],
                })
                try:
                    rec["usd"][key] = int(r["data"]) * 1000  # HERD is published in thousands of dollars
                except ValueError:
                    rec["usd"][key] = None
                if r["status"] and r["status"] not in rec["status"]:
                    rec["status"].append(r["status"])
    except zipfile.BadZipFile:
        raise ParseError("HERD download is not a valid archive.") from None
    by_unitid = {v["unitid"]: v for v in insts.values() if v["unitid"]}
    unmatched = [{"name": v["name"], "state": v["state"], "form": v["form"], "total_usd": v["usd"].get("total")}
                 for v in insts.values() if not v["unitid"]]
    return {"year": year, "institutions": by_unitid, "unmatched": unmatched}


async def _index(guard: Guard) -> Loaded:
    name = "herd-index.json"
    hit = cache.read(name)
    if hit and cache.is_fresh(hit["meta"], 14):
        return Loaded(hit["data"], hit["meta"], False)
    try:
        body, url = await guard.get_bytes(PAGE, max_bytes=3_000_000)
        files = pick_files(body.decode("utf-8", "replace"))
    except UpstreamError:
        if hit:
            return Loaded(hit["data"], hit["meta"], True)
        raise
    data = {str(y): v for y, v in files.items()}
    return Loaded(data, cache.write(name, data, f"latest file year {max(files)}", url), False)


async def available_years(guard: Guard) -> list[int]:
    return sorted(int(y) for y in (await _index(guard)).data)


async def year(guard: Guard, y: int) -> Loaded:
    name = f"herd-{y}.json"
    hit = cache.read(name)
    if hit and cache.is_fresh(hit["meta"], TTL_DAYS):
        return Loaded(hit["data"], hit["meta"], False)
    try:
        files = (await _index(guard)).data.get(str(y))
        if not files or "standard" not in files:
            raise UpstreamError(f"HERD has no standard-form file listed for FY{y}.")
        raw, url = await guard.get_bytes(BASE + files["standard"], max_bytes=MAX_ZIP_BYTES)
        parsed = parse_zip(raw, y, "standard")
        sha = {"file_sha256": hashlib.sha256(raw).hexdigest(), "file_bytes": len(raw)}
        if "short" in files:
            sraw, _ = await guard.get_bytes(BASE + files["short"], max_bytes=MAX_ZIP_BYTES)
            sp = parse_zip(sraw, y, "short")
            for k, v in sp["institutions"].items():
                parsed["institutions"].setdefault(k, v)
            parsed["unmatched"] += sp["unmatched"]
            sha["short_file_sha256"] = hashlib.sha256(sraw).hexdigest()
    except UpstreamError:
        if hit:
            return Loaded(hit["data"], hit["meta"], True)
        raise
    return Loaded(parsed, cache.write(name, parsed, f"HERD FY{y}", url, **sha), False)
