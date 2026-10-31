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
