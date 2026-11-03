# Testing record: highered-institutions v0.1.0

Test institution: **Test Community College A** (UNITID 999001).

## Automated (fixture-based) — `PYTHONPATH=src uv run --no-sync pytest`
Result on 2026-10-31: **40 passed, 1 skipped** (the skipped one is the opt-in live test).

Covers: resolution by name, UNITID, OPEID8, OPEID6, EIN, UEI, and domain; ambiguity returns all candidates and `resolved: false`; one-to-many OPEID8 (South University-Savannah campuses); partial names never auto-resolve; profile degrades to explicit nulls without a Scorecard key; the key is sent in a header and never appears in URLs or output; trend nulls; deterministic peers; stale-cache fallback; checksum tampering.

Negative tests (all must fail safely, and fail before any network call): malformed/oversized UNITID, injection-style strings, wrong enum values, out-of-range numbers; a non-allowlisted host; non-HTTPS URL; URL with credentials; redirect to another host (the other host is never contacted); redirect to HTTP; oversized response; bounded retries without leaking URL/key/paths; cache path traversal (`..`, absolute, subdirectory, uppercase, overlong, symlink escape).

Fixtures were recorded from live responses on 2026-10-31 (`tests/record_fixtures.py`) and contain no keys (keys are sent in a header and are not part of response bodies).

## Live (opt-in) — `HIGHERED_LIVE=1 COLLEGE_SCORECARD_API_KEY=... pytest -m live`
Run 2026-10-31: **1 passed** (cold cache: 85 s, dominated by 1 request/second pacing for 10 enrollment years).

Verified live against real upstreams:
- Name resolution of Test Community College A -> UNITID 999001, OPEID 09990100, EIN 999000001, UEI TESTCOLLEG1A.
- Enrollment trend 2016-2024 returned (2024 = 2,044; 2023 = 1,711).
- `compare_peers` returned 5 public community-college peers (Carnegie 2025 basic class 12).
- Scorecard profile fields returned for 999001 with a real key (1,000/hour limit header observed).
- End-to-end MCP stdio session through `uvx --from <local path> highered-institutions`: initialize, tools/list (5 tools), a successful tools/call, and a rejected malformed call.

## get_financial_snapshot
- Fixture tests: GASB-style public (Test College A) and FASB-style private (Harvard) headline figures, basis named from which net-position field is populated, per-field nulls with reasons for fields the form does not carry, unknown UNITID rejected, no-record case.
- Live: Test College A FY2023 revenues 46,181,628 and net position 61,681,116; Harvard FY2023 revenues 9,433,391,104.
- Observed: `form_type` does not track sector (Penn State, a public institution, reports FASB-style `equity_end`), so the tool reports which field was populated rather than inferring sector or basis from codes.

## Found while testing
- Full-width digits (e.g. `１６７６３１`) are rejected as UNITIDs (they used to satisfy `\d`); regression cases for `get_enrollment_trend` and `get_financial_snapshot`.

## Review fixes (2026-10-31, after a test brief for Test College A)
- `get_financial_snapshot(years=N)`: history table, revenue components and capital appropriations as reported; `revenues_minus_expenses` computed from reported totals and labeled. Live Test College A FY2019-23: +2.94M, -5.09M, -2.40M, +1.14M, +0.74M while net position fell from 67.8M to 60.3M before partly recovering. Found that Urban's revenue components reconcile to total revenue in FY2020 and FY2023 but not FY2019, FY2021 or FY2022 (in FY2022 total revenue equals operating plus nonoperating with no additions line even though capital appropriations of 4.1M were reported), so no "excluding capital" figure is computed.
- `compare_peers(scope='same_state'|'same_system')`: narrowed scopes match on control and institution level (Carnegie class relaxed, and the returned rule says so). Live: Test College A ranks 1 of 11 in the Massachusetts Community Colleges system for 2019-2024 (+22.1% vs a peer median of +2.3%); the national size-match gave a peer median of -6.6%.

## Found while verifying the fixes
- `uvx --from <local path>` reused a stale build after source edits (uv only watched `pyproject.toml`), so a stdio session ran code without the new `scope` option. Fixed for all four servers with `[tool.uv] cache-keys` including `src/**/*.py`; verified by a stdio launch that then exercised the new options.

## Source behavior reported, not worked around
1. Urban `robots.txt` lists `Disallow: /api/`. Owner decision (2026-10-31): call Urban once per quarter (cache TTL 90 days) with 1 request/second pacing; NCES/IPEDS as backup. Contacting Urban to confirm is recommended.
2. Urban returns **HTTP 500** (not 404) for a year not yet published (fall enrollment 2025). The year-detection probe treats a failure as "not published" for that probe only; data requests still surface errors.
3. Urban silently ignores `inst_name` filters, so name search is done locally over the cached directory.
4. Scorecard `accreditor` was absent for the probed institutions.

## Not verified
- `.mcpb` bundle: manifest written to the MCPB spec (v0.4 `uv` server type) but **not packed or loaded in a host**.
- PyPI trusted publishing: workflow written, **not run** (nothing published).
- GitHub Actions workflows have not run (no remote yet).
- Carnegie code labels (codes only are returned).
- Windows behavior.
- `ueis` format with multiple values per institution (parser splits on commas, semicolons, and spaces).
- The NCES/IPEDS fallback is **not implemented** in this milestone; the only outage protection is serving the stale cached copy with a warning.

## get_retention (Milestone 4)
- 26 fixture tests in `tests/test_retention.py`: the rate, retained count, cohort and flag as published, the revised file winning over the provisional one, newest-year discovery and caching, years before the files exist as nulls, flag A as not applicable, blanks and unknown flags as nulls with their meaning, an institution absent from the file, imputed flags warned about, very small cohorts warned about, no call to Urban (the tool still answers when Urban is down), 11 malformed inputs rejected before any request, exact archive member names (`../`, subfolders, wrong case, other years refused), zip bomb and entry-count limits, a CSV with missing columns, no rows or junk ids, oversized and non-zip downloads, a redirect or other host refused, year and cache-name bounds, the first-download deadline, and the tool's two inputs only.
- Mutation checks (2026-11-03): removing the member-name anchor, the `_rv` preference, the uncompressed-size cap, the entry-count cap, the UNITID filter, the year bounds or the required-columns check each makes a test fail.
- Live, empty cache (2026-11-03): Test College A five years in 7.4 s including the probes for unpublished years; later colleges 0.0 s from cache. Values match an independent read of the raw files (see docs/sources.md).
