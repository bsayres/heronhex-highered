import json
import os
from pathlib import Path

import httpx
import pytest

from highered_institutions import server

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text())


class Upstream:
    """Serves recorded responses and remembers every request made."""

    def __init__(self):
        self.directory = load("directory.json")
        self.enrollment = load("enrollment.json")
        self.finance = load("finance_2023.json")
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
                if year != "2023":
                    return httpx.Response(500)
                row = self.finance.get(q.get("unitid"))
                return httpx.Response(200, json={"count": 1 if row else 0, "next": None, "results": [row] if row else []})
            else:  # fall-enrollment: latest year has no data yet in these fixtures
                table = self.enrollment.get(year)
                if table is None:
                    return httpx.Response(404)
                rows = [{"unitid": int(u), "enrollment_fall": v} for u, v in table.items()]
            if "unitid" in q:
                rows = [r for r in rows if str(r["unitid"]) == q["unitid"]]
            return httpx.Response(200, json={"count": len(rows), "next": None, "results": rows})
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
