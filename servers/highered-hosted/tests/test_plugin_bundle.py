"""The code-free plugin bundle (plugin-hosted/) stays in step with the servers: same skills, the live URL, no code files."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "plugin-hosted"
SERVERS = ["highered-institutions", "highered-risk", "highered-accreditation", "highered-funding", "highered-labor-market"]


def test_skills_are_exact_copies_of_the_servers_skills():
    for name in SERVERS:
        assert (BUNDLE / "skills" / name / "SKILL.md").read_bytes() == (ROOT / "servers" / name / "SKILL.md").read_bytes(), name
    src = ROOT / "skills" / "institution-brief"
    for p in src.rglob("*"):
        if p.is_file() and p.name != ".DS_Store":
            assert (BUNDLE / "skills" / "institution-brief" / p.relative_to(src)).read_bytes() == p.read_bytes(), p.name


def test_bundle_points_at_the_hosted_url_and_declares_no_local_server():
    mcp = json.loads((BUNDLE / ".mcp.json").read_text())
    assert mcp == {"mcpServers": {"heronhex-highered": {"type": "http", "url": "https://mcp.heronhex.com/mcp"}}}
    manifest = json.loads((BUNDLE / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "heronhex-highered-hosted" and manifest["license"] == "MIT"
    assert "userConfig" not in manifest and "mcpServers" not in manifest
    assert (BUNDLE / manifest["icon"]).is_file() and (BUNDLE / "LICENSE").is_file()
    assert len((BUNDLE / "README.md").read_text().split()) >= 40


def test_bundle_holds_only_text_files_and_the_icon():
    allowed = {".md", ".json", ".html", ".png"}
    for p in BUNDLE.rglob("*"):
        if p.is_file():
            assert p.suffix in allowed or p.name == "LICENSE", p
            assert p.stat().st_size < 256 * 1024, p
            assert p.name not in (".DS_Store", "Thumbs.db"), p
