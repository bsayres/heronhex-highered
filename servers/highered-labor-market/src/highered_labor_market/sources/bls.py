"""BLS Employment Projections: Table 1.2 occupational projections and worker characteristics (national)."""
import re

from ..http import Guard
from ._load import Loaded, load, sha256
from ._xlsx import MAX_FILE_BYTES, ParseError, open_workbook

URL = "https://www.bls.gov/emp/ind-occ-matrix/occupation.xlsx"
SOURCE = "BLS Employment Projections (National Employment Matrix)"
CODE_RE = re.compile(r"^[0-9]{2}-[0-9]{4}\Z")


def _num(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _text(v) -> str | None:
    s = str(v).strip() if v is not None else ""
    return None if s in ("", "—", "-") else s


def parse(data: bytes) -> dict:
    wb = open_workbook(data)
    if "Table 1.2" not in wb.sheetnames:
        raise ParseError("BLS workbook does not have the expected table.")
    rows = list(wb["Table 1.2"].iter_rows(values_only=True))
    if len(rows) < 3:
        raise ParseError("BLS table had no data rows.")
    title = str(rows[0][0] or "")
    period = re.search(r"([0-9]{4})[–-]([0-9]{2,4})", title)
    header = [str(h or "") for h in rows[1]]

    def col(prefix: str, nth: int = 0) -> int:
        hits = [i for i, h in enumerate(header) if h.startswith(prefix)]
        if len(hits) <= nth:
            raise ParseError("BLS table does not have the expected columns.")
        return hits[nth]

    ix = {"code": 1, "name": 0, "type": col("Occupation type"),
          "emp_base": col("Employment, 20", 0), "emp_proj": col("Employment, 20", 1), "openings": col("Occupational openings"),
          "wage": col("Median annual wage"), "education": col("Typical education needed"),
          "experience": col("Work experience in a related"), "training": col("Typical on-the-job training")}
    occ: dict[str, dict] = {}
    for r in rows[2:]:
        code = str(r[ix["code"]] or "").strip()
        if not CODE_RE.match(code) or str(r[ix["type"]] or "") != "Line item":
            continue
        occ[code] = {
            "title": str(r[ix["name"]]).strip(), "employment_base_thousands": _num(r[ix["emp_base"]]), "employment_projected_thousands": _num(r[ix["emp_proj"]]),
            "annual_openings_thousands": _num(r[ix["openings"]]), "median_annual_wage_usd": _num(r[ix["wage"]]),
            "entry_education": _text(r[ix["education"]]), "work_experience": _text(r[ix["experience"]]), "on_the_job_training": _text(r[ix["training"]]),
        }
    if not occ:
        raise ParseError("BLS table had no occupation rows.")
    base, end = (period.group(1), period.group(2)) if period else ("", "")
    return {"occupations": occ, "projection_period": f"{base}-{end}" if period else None, "title": title[:160]}


async def get(guard: Guard) -> Loaded:
    async def fetch():
        raw, url = await guard.get_bytes(URL, max_bytes=MAX_FILE_BYTES)
        parsed = parse(raw)
        return parsed, f"projections {parsed['projection_period'] or 'period unknown'}", url, {"file_sha256": sha256(raw)}

    return await load("bls-projections.json", 90, fetch)


def lookup(occupations: dict, soc: str) -> tuple[dict | None, str | None, str]:
    """(record, bls_code, how) for a 6-digit SOC: exact line item, else its broad group (last digit 0), else none."""
    if soc in occupations:
        return occupations[soc], soc, "exact"
    broad = soc[:-1] + "0"
    if broad in occupations:
        return occupations[broad], broad, "broad_group"
    return None, None, "none"
