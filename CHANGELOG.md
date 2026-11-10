# Changelog

Format follows Keep a Changelog. The five servers are released to PyPI together as `heronhex-*` packages.

## [0.1.1] - 2026-11-10

### Changed
- The three plugin settings default to empty so servers that reference them still load where the app does not prompt (Cowork); removed the unused MCPB leftovers (`manifest.json`, `src/main.py`) from each server.
- Plugin servers now start with `uv run --locked --no-dev --project <server folder>` against each server's committed `uv.lock`, instead of `uvx` with a PyPI version. The directory's validator treats a PyPI version alone as not pinned; a locked project shipped in the plugin is a pin it accepts. Cold start is about 3 s.
- Release metadata only, no code change: project links (homepage, issues, privacy) on the PyPI pages, `homepage`, `documentationUrl` and `privacyPolicyUrl` in the plugin manifest, a `marketplace.json` so the plugin installs from this repository, and a short About section in the README.

## [0.1.0] - 2026-11-10 (first PyPI release)

### Changed
- Repository renamed `heronhex-highered` (was `highered-mcps`) to match the plugin and packages; repository, support and citation URLs updated.
- Removed the `mcpb` workflow: the directory no longer accepts `.mcpb` bundles, and its manifest failed validation on every release tag. `manifest.json` and `src/main.py` in each server are left in place.
- Tests, fixtures and docs no longer name the institutions used during development: names and identifiers are neutral placeholders (`Test College A`, UNITID 999001 and so on). Live tests and fixture recording read their target from `HIGHERED_LIVE_*` variables (see `.env.example`) and skip when unset. The Urban year probes use a fixed large institution (`PROBE_UNITID`). Working notes that name test colleges moved to the gitignored `docs/internal/`.
- PyPI distribution names are now `heronhex-institutions`, `heronhex-risk`, `heronhex-accreditation`, `heronhex-funding` and `heronhex-labor` (all unclaimed on PyPI on 2026-11-10). Command names, Python modules, folders, MCP server names and skill names are unchanged, so existing Desktop configs keep working. The registry names became `io.github.bsayres/heronhex-*`.

### Added
- Plugin scaffold `heronhex-highered`: `.claude-plugin/plugin.json` (name, `userConfig` for the three optional keys, marked sensitive), `.mcp.json` (five servers, `uvx` pinned to `==0.1.0` from PyPI), an icon (the heron and hexagon mark, 1024 px square), skills loaded from the existing `servers/*/SKILL.md` and `skills/institution-brief`, and `docs/privacy-policy.md`. Not runnable from the marketplace until the servers are on PyPI.
- `search_occupations` (labor-market): find a SOC code from words in the occupation title (light stemming), so a question in plain words can reach `get_wages`; the `get_wages` description now names the plain questions it answers.
- `get_retention` (institutions): fall-to-fall retention rates, cohorts, student-to-faculty ratio and IPEDS flags from NCES's complete data files (`EF{year}D.zip`), read in memory by exact member name; adds `nces.ed.gov` to the institutions allowlist. Independent of the Urban API.
- `get_wages` and `search_metros` (labor-market): BLS OEWS wages and employment for an occupation in a state or metropolitan area (May 2025), with suppressed cells as nulls and top-coded wages flagged as floors; `cbsa` on `resolve_institution` and `get_institution_profile` so an institution joins to its metro.
- `get_finding_text` (risk): opt-in FAC finding narratives and the auditee's corrective action plan for one report; exact report id, capped and cleaned text, untrusted-text notice, names warning.
- `highered-accreditation` server (DAPIP status and actions, programmatic and state-board records, `last_action` per record).
- `search_programs` (labor-market): find a CIP code from plain words, from the cached NCES crosswalk.
- `find_program_offerings` (labor-market): who else offers a program at a credential level, optional state, ranked by awards with ties; incomplete lists are marked and unranked.
- `compare_institutions` (institutions): 2 to 5 named colleges side by side, with warnings about differing control, accounting basis and finance year.
- `institution_brief` MCP prompt (institutions) and the `institution-brief` skill with an interactive dashboard template, one-page view and print layout.
- A `kind` on every null (suppressed, not_reported, not_applicable, not_found, not_configured, source_unavailable, not_covered) and `null_counts` on every response.
- Tool `title` on all tools; `server.json` (MCP Registry draft, schema-validated) and `mcp-name` line in each server README.
- `DEMO_KEY` fallback for the Scorecard and FAC calls, with a warning in every response that used it.

### Changed
- Skill descriptions for labor-market, institutions and risk now name the plain questions they answer (wages by state or metro, retention, audit finding text), since the description is what routes a question to a skill.
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
- `get_wages` and `search_metros` (labor-market) read the nonmetropolitan areas workbook (`BOS_M2025_dl.xlsx`) as well as the metropolitan one. The first version read only the metropolitan file, so the 7-digit nonmetropolitan codes the tool described did not exist in real data.
- A superseded accreditation record could be read as a loss; each record now carries its last recorded action.

### Not done
- Clery data (decision: skipped), Financial Value Transparency (no usable public file), IPEDS direct-file backup source, accreditor-directory checks, PyPI release, directory submission.
