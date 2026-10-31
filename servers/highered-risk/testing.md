# Testing record: highered-risk v0.1.0 (part 1: `get_fsa_status` only)

## Automated (fixture-based) — `PYTHONPATH=src uv run --no-sync pytest`
Result on 2026-10-31: **23 passed, 1 skipped** (opt-in live test).
Fixtures are synthetic workbooks built in `tests/conftest.py` with the same column layout as the real FSA files (an `.xls` is produced with the dev-only `xlwt`). No real FSA files are committed.

Covers: link discovery picks the newest HCM and composite files; HCM listed / sibling campuses on the same OPEID6; composite score and fiscal-year-end date decoding from `.xls`; default-rate lookup by OPEID6; explicit nulls with reasons for public institutions; per-section sources with file SHA-256; free text returned only as data and never in tool descriptions; cache reuse; stale-cache fallback; checksum tamper detection.

Negative tests: malformed OPEID (7/9 digits, letters, traversal, injection-style, trailing space) rejected before any network call; discovered links containing `..` or outside `/sites/default/files/`; no matching link on the page; non-zip and zip-bomb workbooks; wrong-format `.xls`; oversized download; non-allowlisted host; redirect to another host (never contacted); cache path traversal and uppercase/absolute names.
A real bug was found by these tests and fixed: the first version of the file-path pattern accepted `..` segments.

## Live (opt-in) — `HIGHERED_LIVE=1 pytest -m live`
Run 2026-10-31: **1 passed** (22 s cold, mostly the 7-second crawl-delay pacing).

Verified live:
- HCM list as of **2026-06-01** (491 rows on the "All HCM" sheet): Alabama A&M (OPEID 00100200) listed, "HCM - Cash Monitoring 1", reason "Compliance Audit Late or Missing" per the file.
- Composite scores file for fiscal years 7/1/2022 to 6/30/2023, data as of Dec 17 2024: Alaska Bible College (00884300) score 2.2, fiscal year end 2023-05-31.
- FY2023 cohort default rates (4,579 schools): Alabama A&M 0.8% for the FY2023 cohort.
- Test Community College A (09990100, public): not on HCM; no composite score (public institutions not scored); OPEID6 099901 absent from the FY2023 default rate file. All reported as nulls with reasons. **Why Test College A is absent from the CDR file is not established**; the tool says only that it is not in the file.
- End-to-end MCP stdio session via `uvx --from <local path> highered-risk`: tools/list, a successful call, a rejected malformed call.

## Source behavior reported
1. studentaid.gov Data Center pages are JavaScript apps. File lists are available as page-content JSON at `<page>.json` (undocumented). Used with a clear failure if the layout changes. The file's own links are the only source of file URLs.
2. studentaid.gov over HTTP/2 intermittently failed for plain clients (`INTERNAL_ERROR`) during research; httpx worked in tests. Not reproduced in the server runs.
3. Composite scores are published about two years late and only as legacy `.xls`.
4. The CDR workbook declares ~1M rows but has ~4.6k; the parser stops at the first blank row.
5. studentaid.gov `robots.txt` has `Crawl-delay: 7`; the server paces to it.

## Not verified / not built
- **`get_audit_findings` (Federal Audit Clearinghouse) is not built**: no FAC API key was available to verify endpoint paths, filters, and field names live (docs name the `general` and `findings` tables and an `X-Api-Key` header; unauthenticated calls return 403).
- Older and newer HCM/composite layouts than those above; the `.xlsx` variant of composite scores.
- `.mcpb` bundle, PyPI publishing, GitHub Actions: not run.
