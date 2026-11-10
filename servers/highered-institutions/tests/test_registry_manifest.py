import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_server_json_matches_the_package_and_readme():
    sj = json.loads((ROOT / "server.json").read_text())
    proj = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    pkg = sj["packages"][0]
    assert pkg["registryType"] == "pypi" and pkg["identifier"] == proj["name"] and pkg["version"] == proj["version"] == sj["version"]
    assert pkg["transport"] == {"type": "stdio"}
    assert sj["name"].startswith("io.github.bsayres/") and sj["name"].endswith("/" + proj["name"])
    assert f"<!-- mcp-name: {sj['name']} -->" in (ROOT / "README.md").read_text()  # ownership check the registry reads from PyPI
    assert 0 < len(sj["description"]) <= 100
    assert sj["repository"]["subfolder"] == "servers/" + ROOT.name


def test_listed_environment_variables_are_only_those_the_code_reads():
    sj = json.loads((ROOT / "server.json").read_text())
    src = "\n".join(p.read_text() for p in (ROOT / "src").rglob("*.py"))
    for v in sj["packages"][0]["environmentVariables"]:
        assert re.search(r'"' + v["name"] + r'"', src), v["name"]
        assert v["isRequired"] is False
        if v["name"].endswith(("_KEY", "_CONTACT")):
            assert v["isSecret"] is True
