# Changelog

Format follows Keep a Changelog. Versions are not yet released to PyPI; every server is 0.1.0 in `pyproject.toml`.

## [Unreleased]

### Added
- `get_finding_text` (risk): opt-in FAC finding narratives and the auditee's corrective action plan for one report; exact report id, capped and cleaned text, untrusted-text notice, names warning.
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

### Changed
- `get_title_iv_status` quotes the cohort default rate sanction rule (34 CFR 668.206(a)) in a `reference` block; `get_audit_findings` returns `auditee_ein` and `auditee_uei` and warns when the rows under one identifier belong to more than one auditee; both accreditation tools return `action_history` and records carry a `review_date_note` when a current record's review date is over five years past.
- `search_funding_opportunities` and `search_grant_awards`: clearer filter and truncation warnings, a note on close dates years away, and HTML entities in titles decoded to plain text.
- All five server skills, the `institution-brief` skill and the `institution_brief` prompt: shared answer rules (lead with what the figures are, label anything a tool did not return, show arithmetic, name both years when comparing sources, no lookups of named people, UEI first for audits).
- `highered-institutions` reliability: single-institution Urban rows are cached for a day, years are fetched at once, small requests time out after 12 s and retry, a tool call answers within 45 seconds with partial results and unfinished work keeps loading in the background, and `get_enrollment_trend` asks for one institution instead of downloading every institution on a first call (cold-cache time 84 s to about 10 s).
- `highered-risk`, `highered-funding`, `highered-accreditation`: the same 45-second deadline as the institutions server. Risk reads its three FSA files at once and returns the sections that arrived (a missing one is a `source_unavailable` null; an oversized file is now a null instead of a failed call); funding reads HERD years at once; first-time downloads that run long say so and finish in the background. Cold first calls: HERD five years 44 s to 15-19 s; accreditation about 24 s and risk about 21 s are unchanged (one file dominates).

### Fixed
- A superseded accreditation record could be read as a loss; each record now carries its last recorded action.

### Not done
- Clery data (decision: skipped), Financial Value Transparency (no usable public file), IPEDS direct-file backup source, accreditor-directory checks, PyPI release, directory submission.
