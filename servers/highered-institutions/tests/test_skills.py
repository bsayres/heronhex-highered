"""Guards on the skill files: every server carries the shared answer rules, and fields the skills name exist in the code."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SERVERS = sorted((ROOT / "servers").glob("highered-*/SKILL.md"))
HEADING = "## Rules that apply to every answer"
CORE = ("Open with what the figures are, not a conclusion", "did not return is not from these tools", "Show your arithmetic",
        "Comparing sources", "Outside these tools", "never\" and \"should we worry\"")


def test_all_five_server_skills_are_found():
    assert len(SERVERS) == 5


@pytest.mark.parametrize("skill", SERVERS, ids=lambda p: p.parent.name)
def test_each_server_skill_carries_the_shared_rules(skill):
    text = skill.read_text()
    assert HEADING in text
    assert all(c in text for c in CORE), [c for c in CORE if c not in text]


def test_brief_skill_and_prompt_carry_the_writing_rules():
    text = (ROOT / "skills" / "institution-brief" / "SKILL.md").read_text()
    assert "## Writing rules for the summary and every section" in text and "UEI first" in text
    prompt = (ROOT / "servers" / "highered-institutions" / "src" / "highered_institutions" / "prompts.py").read_text()
    assert "not a conclusion" in prompt and "named people" in prompt and "action_history" in prompt


@pytest.mark.parametrize("name,server", [
    ("action_history", "highered-accreditation"), ("review_date_note", "highered-accreditation"),
    ("cohort_default_rate_sanction_rule", "highered-risk"), ("auditee_name", "highered-risk"),
])
def test_field_names_the_skills_use_exist_in_the_servers(name, server):
    skill = (ROOT / "servers" / server / "SKILL.md").read_text()
    code = "".join(f.read_text() for f in (ROOT / "servers" / server / "src").rglob("*.py"))
    assert name in skill and name in code


@pytest.mark.parametrize("server", ["institutions", "risk", "accreditation", "funding", "labor-market"])
def test_each_server_says_what_questions_it_covers(server):
    """The host routes a question to a server from its instructions and tool descriptions, so each says in plain words what it covers."""
    text = (ROOT / "servers" / f"highered-{server}" / "src" / f"highered_{server.replace('-', '_')}" / "server.py").read_text()
    block = text[text.index("instructions=("):text.index("),\n)", text.index("instructions=("))]
    assert "Covers:" in block and len(block) < 1400


def test_the_wage_server_names_wages_and_the_institutions_server_names_retention():
    root = ROOT / "servers"
    assert "what workers in an occupation earn" in (root / "highered-labor-market/src/highered_labor_market/server.py").read_text()
    assert "retention" in (root / "highered-institutions/src/highered_institutions/server.py").read_text().split("instructions=(")[1][:900]
