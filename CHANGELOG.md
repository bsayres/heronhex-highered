# Changelog

Format follows Keep a Changelog. Versions are not yet released to PyPI; every server is 0.1.0 in `pyproject.toml`.

## [Unreleased]

### Added
- `highered-accreditation` server (DAPIP status and actions, programmatic and state-board records, `last_action` per record).
- `search_programs` (labor-market): find a CIP code from plain words, from the cached NCES crosswalk.
- `find_program_offerings` (labor-market): who else offers a program at a credential level, optional state, ranked by awards with ties; incomplete lists are marked and unranked.
- `compare_institutions` (institutions): 2 to 5 named colleges side by side, with warnings about differing control, accounting basis and finance year.
- `institution_brief` MCP prompt (institutions) and the `institution-brief` skill with an interactive dashboard template, one-page view and print layout.
- A `kind` on every null (suppressed, not_reported, not_applicable, not_found, not_configured, source_unavailable, not_covered) and `null_counts` on every response.
- Tool `title` on all tools; `server.json` (MCP Registry draft, schema-validated) and `mcp-name` line in each server README.
- `DEMO_KEY` fallback for the Scorecard and FAC calls, with a warning in every response that used it.
- Three-college validation record (`docs/validation-2026-10-31.md`) and a 20-question leader test (`docs/question-test-2026-11-01.md`).

### Changed
- `get_fsa_status` renamed `get_title_iv_status`.
- Several tool descriptions reworded from directives to plain statements.
- Composite-score null reason no longer implies only public institutions are missing.

### Fixed
- A superseded accreditation record could be read as a loss; each record now carries its last recorded action.

### Not done
- Clery data (decision: skipped), Financial Value Transparency (no usable public file), IPEDS direct-file backup source, accreditor-directory checks, PyPI release, directory submission.
