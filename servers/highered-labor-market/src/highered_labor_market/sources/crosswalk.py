"""NCES + BLS CIP 2020 to SOC 2018 crosswalk. Not based on empirical data (NCES)."""
import re

from ..http import Guard
from ._load import Loaded, load, sha256
from ._xlsx import MAX_FILE_BYTES, ParseError, open_workbook

URL = "https://nces.ed.gov/ipeds/cipcode/Files/CIP2020_SOC2018_Crosswalk.xlsx"
SOURCE = "NCES/BLS CIP 2020 to SOC 2018 Crosswalk"
CIP_RE = re.compile(r"^[0-9]{2}\.[0-9]{4}\Z")
SOC_RE = re.compile(r"^[0-9]{2}-[0-9]{4}\Z")
NO_MATCH = "99-9999"


def parse(data: bytes) -> dict:
    wb = open_workbook(data)
    if "CIP-SOC" not in wb.sheetnames:
        raise ParseError("Crosswalk workbook does not have the expected sheet.")
    rows = wb["CIP-SOC"].iter_rows(values_only=True)
    header = list(next(rows, ()))
    if header[:4] != ["CIP2020Code", "CIP2020Title", "SOC2018Code", "SOC2018Title"]:
        raise ParseError("Crosswalk workbook does not have the expected columns.")
    mapped: dict[str, dict] = {}
    unmatched: dict[str, str] = {}
    for r in rows:
        if not r or not r[0]:
            continue
        cip, ctitle, soc, stitle = (str(x).strip() if x is not None else "" for x in r[:4])
        if not CIP_RE.match(cip):
            continue
        rec = mapped.setdefault(cip, {"title": ctitle, "socs": []})
        if soc == NO_MATCH:
            unmatched[cip] = ctitle
        elif SOC_RE.match(soc):
            rec["socs"].append([soc, stitle])
    if not mapped:
        raise ParseError("Crosswalk sheet had no data rows.")
    return {"programs": {k: v for k, v in mapped.items() if v["socs"]}, "unmatched": unmatched}


async def get(guard: Guard) -> Loaded:
    async def fetch():
        raw, url = await guard.get_bytes(URL, max_bytes=MAX_FILE_BYTES)
        return parse(raw), "CIP 2020 / SOC 2018", url, {"file_sha256": sha256(raw)}

    return await load("crosswalk.json", 365, fetch)


def search(data: dict, keyword: str, limit: int) -> tuple[list[dict], int]:
    """CIP 2020 programs whose title contains every word of `keyword` (case-insensitive substring). Returns (rows, total matches)."""
    words = [w for w in re.split(r"[^a-z0-9]+", keyword.lower()) if w]
    if not words:
        return [], 0
    phrase = " ".join(words)
    entries = [(cip, rec["title"], len(rec["socs"])) for cip, rec in data["programs"].items()]
    entries += [(cip, title, 0) for cip, title in data["unmatched"].items() if cip not in data["programs"]]
    hits = []
    for cip, title, n in entries:
        t = " ".join(re.split(r"[^a-z0-9]+", title.lower())).strip()
        if all(w in t for w in words):
            rank = (0 if phrase in t else 1, 0 if t.startswith(words[0]) else 1, cip)
            hits.append((rank, {"cip6": cip, "cip4": cip[:5], "title": title.rstrip("."), "occupations_mapped": n}))
    hits.sort(key=lambda h: h[0])
    return [h[1] for h in hits[:limit]], len(hits)
