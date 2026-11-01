from pathlib import Path

from highered_institutions import models

SRC = Path(models.__file__).parent


def test_every_null_in_the_source_declares_a_kind():
    missing = []
    for p in SRC.rglob("*.py"):
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if '"field":' in line and '"kind"' not in line:
                missing.append(f"{p.name}:{i}")
    assert not missing, missing


def test_envelope_counts_kinds_and_flags_unknown_ones():
    src = [{"source": "s", "source_url": "https://example.com", "as_of": "x", "retrieved_at": "2026-01-01T00:00:00+00:00"}]
    env = models.envelope(src, {}, [
        {"field": "a", "kind": "suppressed", "reason": "r"},
        {"field": "b", "kind": "suppressed", "reason": "r"},
        {"field": "c", "kind": "made_up", "reason": "r"},
        {"field": "d", "reason": "r"},
    ])
    assert [n["kind"] for n in env["nulls"]] == ["suppressed", "suppressed", "unclassified", "unclassified"]
    assert env["null_counts"] == {"suppressed": 2, "unclassified": 2}
    assert models.envelope(src, {})["null_counts"] == {}
    assert {n["kind"] for n in env["nulls"]} - {"unclassified"} <= models.NULL_KINDS
