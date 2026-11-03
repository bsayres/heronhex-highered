import csv
import io
import json
import os
import re
import zipfile
from pathlib import Path

import httpx
import pytest

from highered_institutions import server

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text())


EF_HEADER = ["UNITID", "XGRCOHRT", "GRCOHRT", "XUGENTER", "UGENTERN", "XPGRCOHR", "PGRCOHRT", "XRRFTCT", "RRFTCT", "XRRFTEX", "RRFTEX", "XRRFTIN", "RRFTIN", "XRRFTCTA", "RRFTCTA",
             "XRET_NMF", "RET_NMF", "XRET_PCF", "RET_PCF", "XRRPTCT", "RRPTCT", "XRRPTEX", "RRPTEX", "XRRPTIN", "RRPTIN", "XRRPTCTA", "RRPTCTA", "XRET_NMP", "RET_NMP",
             "XRET_PCP", "RET_PCP", "XSTUFACR", "STUFACR "]


def ef_row(unitid, ft=(39, 42, 108, "R"), pt=(21, 21, 99, "R"), sfr=(14, "R")):
    d = dict.fromkeys(EF_HEADER, "")
    d.update({"UNITID": unitid, "RET_PCF": ft[0], "RET_NMF": ft[1], "RRFTCTA": ft[2], "XRET_PCF": ft[3], "RET_PCP": pt[0], "RET_NMP": pt[1], "RRPTCTA": pt[2],
              "XRET_PCP": pt[3], "STUFACR ": sfr[0], "XSTUFACR": sfr[1]})
    return d


def ef_csv(rows: list[dict], header=None) -> str:
    out = io.StringIO()
    out.write("\ufeff")  # NCES files carry a byte-order mark
    w = csv.DictWriter(out, header or EF_HEADER, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def ef_zip(year: int, rows: list[dict], member=None, header=None, extra=()) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in extra:
            z.writestr(name, body)
        z.writestr(member or f"ef{year}d.csv", ef_csv(rows, header))
    return buf.getvalue()


def ef_files() -> dict[int, bytes]:
    """2023 and 2022 are published; 2024 and later are not (NCES answers 404)."""
    return {
        2023: ef_zip(2023, [ef_row("999001"), ef_row("999003", ft=(78, 578, 743, "R"), pt=("", "", "", "A"), sfr=(15, "R")),
                            ef_row("999002", ft=(62, 178, 285, "R"), pt=(46, 109, 238, "R"), sfr=(12, "J")),
                            ef_row("111111", ft=("", "", "", "B"), pt=("", "", "", "H"), sfr=("", "B"))]),
        # the revised file wins over the provisional one that sits beside it
        2022: ef_zip(2022, [ef_row("999001", ft=(41, 50, 122, "R"), pt=(30, 24, 80, "L")), ef_row("999003", ft=(80, 590, 738, "R"), pt=(100, 1, 1, "R"))],
                     member="ef2022d_rv.csv", extra=[("ef2022d.csv", ef_csv([ef_row("999001", ft=(1, 1, 100, "R"))]))]),
    }


class Upstream:
    """Serves recorded responses and remembers every request made."""

    def __init__(self):
        self.directory = load("directory.json")
        self.enrollment = load("enrollment.json")
        self.finance = load("finance.json")
        self.ef = ef_files()
        self.requests: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        host, path, q = req.url.host, req.url.path, dict(req.url.params)
        if host == "educationdata.urban.org":
            parts = path.strip("/").split("/")
            kind, year = parts[4], parts[5]
            if kind == "directory":
                if int(year) > self.directory["year"]:
                    return httpx.Response(404)
                rows = self.directory["results"]
            elif kind == "finance":
                if year not in self.finance:
                    return httpx.Response(500)
                row = self.finance[year].get(q.get("unitid"))
                return httpx.Response(200, json={"count": 1 if row else 0, "next": None, "results": [row] if row else []})
            else:  # fall-enrollment: latest year has no data yet in these fixtures
                table = self.enrollment.get(year)
                if table is None:
                    return httpx.Response(404)
                rows = [{"unitid": int(u), "enrollment_fall": v} for u, v in table.items()]
            if "unitid" in q:
                rows = [r for r in rows if str(r["unitid"]) == q["unitid"]]
            return httpx.Response(200, json={"count": len(rows), "next": None, "results": rows})
        if host == "nces.ed.gov":
            m = re.match(r"^/ipeds/datacenter/data/EF([0-9]{4})D\.zip\Z", path)
            if m and int(m.group(1)) in self.ef:
                return httpx.Response(200, content=self.ef[int(m.group(1))])
            return httpx.Response(404)
        if host == "api.data.gov":
            return httpx.Response(200, json=load("scorecard_999001.json"))
        return httpx.Response(500)


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("COLLEGE_SCORECARD_API_KEY", raising=False)
    up = Upstream()
    server.set_guard(server.Guard(transport=httpx.MockTransport(up), backoff=0, min_interval={}))
    yield up
    server.set_guard(None)


def pytest_collection_modifyitems(config, items):
    if os.environ.get("HIGHERED_LIVE") != "1":
        skip = pytest.mark.skip(reason="live test: set HIGHERED_LIVE=1")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip)
