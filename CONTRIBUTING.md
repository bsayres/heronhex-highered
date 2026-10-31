# Contributing

- Keep it small. Copy existing conventions; duplicate code once before abstracting.
- Python 3.11+. New dependencies need a one-line justification in PLAN.md.
- Every tool returns the standard envelope and explicit nulls with reasons. Never estimate.
- Add the host to a server's allowlist and README together, or not at all.
- Add a negative test for any new input or path.

## Development
```bash
cd servers/highered-institutions
uv sync
PYTHONPATH=src uv run --no-sync pytest          # fixture tests
HIGHERED_LIVE=1 COLLEGE_SCORECARD_API_KEY=... PYTHONPATH=src uv run --no-sync pytest -m live
uv run --no-sync ruff check src tests && uv run --no-sync pip-audit
```
macOS note: if the project lives under a folder macOS flags as hidden-file inheriting, the editable install's `.pth` file can be marked `hidden` and Python skips it (`ModuleNotFoundError`). Using `PYTHONPATH=src` (as above) avoids this; `uvx --from <path>` is unaffected.

Re-record fixtures with `tests/record_fixtures.py`; check that no key appears in them before committing.
