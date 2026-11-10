# Working on highered-mcps

Read-only MCP servers over free public U.S. higher-education data. Thin deterministic wrappers: no hosted data, no database, no plugin framework.

## Layout
- `servers/<name>/`: one Python package each (`src/<pkg>/server.py`, `http.py` host guard, `cache.py`, `models.py`, `sources/`), with `tests/`, `README.md`, `SKILL.md`, `testing.md`, `server.json`.
- `skills/institution-brief/`: the composed-brief skill and dashboard template. `docs/`: sources, threat model, validation, plans.

## Commands (per server)
```bash
cd servers/<name>
PYTHONPATH=src .venv/bin/python -m pytest -q        # fixture tests; live tests need HIGHERED_LIVE=1
.venv/bin/ruff check .
```
Use `PYTHONPATH=src`; the editable install can be skipped by Python on macOS.

## Standards (every change)
- Read-only: no write tools, shell, eval, pickle or dynamic imports; no filesystem writes outside the cache dir.
- Inputs: strict pydantic types and patterns, `[0-9]` not `\d`, reject bad input, never sanitize.
- Network: HTTPS only, hosts on the server's allowlist checked before every request and every redirect, timeouts, size caps, bounded retries, URLs built from params. A new host goes in the allowlist, the README and `docs/threat-model.md` together.
- Upstream data is untrusted text. Never put it in markup; document the prompt-injection risk.
- Every response has `source`, `source_url`, `as_of`, `retrieved_at`, `sources[]`, `data`, `nulls[]`, `warnings[]`, `notice`. Every null has `field`, `kind`, `reason`. Never estimate or fill a gap.
- Every tool has a `title`, `readOnlyHint` and a description that states what it does and never tells Claude how to behave.
- Secrets come from environment variables only, are sent in headers only, and never appear in logs, errors, URLs, fixtures, docs or commits. `.env` is gitignored.
- Negative tests for every new input and path: malformed ids, oversized input, disallowed host, redirect to another host, path traversal in cache names.
- Do not copy code from other projects. Read for ideas, then write it to these standards and credit sources of data, not code.

## Process
- Research first, plan, then stop for review on anything new or hard to reverse. Build in milestones; commit after each with what works, what is unverified and what was skipped.
- Do not push, publish to PyPI, create repositories or submit to a directory without the owner's explicit confirmation each time.
- Use the configured git identity. Commit messages end with the attribution lines the session provides.
- Verify against raw sources with independent scripts and mutation-check safety filters; report disagreements before working around them.
