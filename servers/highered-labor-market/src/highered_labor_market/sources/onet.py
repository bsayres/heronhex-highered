"""O*NET database (CC BY 4.0), downloaded per file from the public bulk files. No API key.

Attribution required by the license: O*NET {version} Database by the U.S. Department of Labor, Employment and Training
Administration (USDOL/ETA), used under the CC BY 4.0 license. This module summarizes the data (top-rated items); it does not alter values.
"""
import csv
import io
import re

from ..http import Guard
from ._load import Loaded, load, sha256
from ._xlsx import ParseError

PAGE = "https://www.onetcenter.org/database.html"
BASE = "https://www.onetcenter.org/dl_files/database"
SOURCE = "O*NET Database (USDOL/ETA), CC BY 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
VERSION_RE = re.compile(r"/dl_files/database/db_([0-9]{2})_([0-9])_excel\.zip")
ONET_RE = re.compile(r"^[0-9]{2}-[0-9]{4}\.[0-9]{2}\Z")
MAX_FILE = 12_000_000
TOP_SKILLS = 40
TOP_TASKS = 30
TOP_TECH = 20


def _rows(raw: bytes, need: set[str]):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig", "replace")))
    if not need <= set(reader.fieldnames or []):
        raise ParseError("O*NET file does not have the expected columns.")
    yield from reader


def _skills(raw: bytes, out: dict, key: str) -> None:
    acc: dict[tuple[str, str], dict] = {}
    for r in _rows(raw, {"O*NET-SOC Code", "Element Name", "Scale ID", "Data Value", "Recommend Suppress"}):
        code = r["O*NET-SOC Code"]
        if not ONET_RE.match(code) or r["Recommend Suppress"] == "Y" or r["Scale ID"] not in ("IM", "LV"):
            continue
        try:
            v = float(r["Data Value"])
        except ValueError:
            continue
        acc.setdefault((code, r["Element Name"]), {})[r["Scale ID"]] = v
    per: dict[str, list] = {}
    for (code, name), s in acc.items():
        if "IM" in s:
            per.setdefault(code, []).append([name, s["IM"], s.get("LV")])
    for code, items in per.items():
        out.setdefault(code, {})[key] = sorted(items, key=lambda x: -x[1])[:TOP_SKILLS]


def parse(files: dict[str, bytes]) -> dict:
    titles: dict[str, str] = {}
    for r in _rows(files["occupation_data"], {"O*NET-SOC Code", "Title"}):
        if ONET_RE.match(r["O*NET-SOC Code"]):
            titles[r["O*NET-SOC Code"]] = r["Title"]
    if not titles:
        raise ParseError("O*NET occupation file had no rows.")
    occ: dict[str, dict] = {c: {"title": t} for c, t in titles.items()}
    _skills(files["essential_skills"], occ, "essential_skills")
    _skills(files["transferable_skills"], occ, "transferable_skills")
    for r in _rows(files["task_statements"], {"O*NET-SOC Code", "Task", "Task Type"}):
        c = r["O*NET-SOC Code"]
        if c in occ and r["Task Type"] == "Core" and len(occ[c].setdefault("core_tasks", [])) < TOP_TASKS:
            occ[c]["core_tasks"].append(r["Task"])
    seen: set[tuple[str, str]] = set()
    for r in _rows(files["software_skills"], {"O*NET-SOC Code", "Workplace Example", "Element Name", "Hot Technology"}):
        c = r["O*NET-SOC Code"]
        if c in occ and r["Hot Technology"] == "Y" and (c, r["Workplace Example"]) not in seen and len(occ[c].setdefault("hot_technologies", [])) < TOP_TECH:
            seen.add((c, r["Workplace Example"]))
            occ[c]["hot_technologies"].append([r["Workplace Example"], r["Element Name"]])
    by_soc: dict[str, list[str]] = {}
    for c in occ:
        by_soc.setdefault(c[:7], []).append(c)
    return {"occupations": occ, "by_soc": by_soc}


async def get(guard: Guard) -> Loaded:
    async def fetch():
        page, page_url = await guard.get_bytes(PAGE, max_bytes=3_000_000)
        found = [(int(a), int(b)) for a, b in VERSION_RE.findall(page.decode("utf-8", "replace"))]
        if not found:
            raise ParseError("Could not find the O*NET database version on its page; the layout may have changed.")
        major, minor = max(found)
        base = f"{BASE}/db_{major:02d}_{minor}_csv"
        files, shas = {}, {}
        for name in ("occupation_data", "essential_skills", "transferable_skills", "software_skills", "task_statements"):
            files[name], _ = await guard.get_bytes(f"{base}/{name}.csv", max_bytes=MAX_FILE)
            shas[name] = sha256(files[name])
        parsed = parse(files)
        parsed["version"] = f"{major}.{minor}"
        return parsed, f"O*NET {major}.{minor} database", page_url, {"file_sha256": sha256(repr(sorted(shas.items())).encode()), "files": shas}

    return await load("onet.json", 180, fetch)
