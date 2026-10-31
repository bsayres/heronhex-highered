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

## get_audit_findings
- 30 fixture tests in `tests/test_fac.py` (fixture recorded live for Test College A, only the requested fields, no contact data). Covers: results by EIN and by UEI; header-only key; no personal-contact fields requested or returned; unknown identifier gives a null with a reason; missing key errors with no request; exactly-one-identifier; malformed or oversized EIN/UEI and `years` out of range rejected before any network call (including filter-injection strings like `eq.1,or=(a.eq.b)`); upstream report ids validated before they are used in a follow-up query; findings truncation reported; redirect to another host blocked without sending the key; errors carry no key or URL; non-list upstream shape fails safely.
- Live (`HIGHERED_LIVE=1`, `FAC_API_KEY` set): Test College A returns 2024 (10 findings, 9 on Pell, 1 on Federal Work-Study), 2023 and 2022 submissions. Stdio session over `uvx` returned the same and rejected a malformed EIN.

## Found while testing
- Full-width digits are rejected as OPEID and EIN (they used to satisfy `\d`); regression cases added.

## Review fixes (2026-10-31, after a test brief for Test College A)
- `filing_timeline` (submitted, certified and accepted dates, months from fiscal year end, the nine-month mark rolled past weekends, days after it) replaces ad hoc date arithmetic by the model, which had mis-stated one filing as 14 months after year end when it was 22.4. Live Test College A: FY2022 submitted 2023-03-29 (8.9 months, 2 days before the mark), FY2023 2024-07-02 (12.1 months, 92 days after), FY2024 2026-05-12 (22.4 months, 407 days after). The rule text is from eCFR 2 CFR 200.512(a); extensions are authorized by the cognizant or oversight agency and are not visible in FAC data, so the warning says "a question to ask, not proof of noncompliance".
- `compliance_requirement_labels` decoded from the FAC API Data Dictionary (A to P, D and K reserved, no O, codes can combine letters); unknown letters give null.
- FAC's definition of `is_modified_opinion` is "the auditor identified the finding as the basis for a modified opinion"; it does not say which opinion, so the tool says so instead of calling it a compliance opinion (an earlier review comment had assumed that).
- Date helper tests include month-ends, weekend roll-forward, a leap-day month-end and a December year end.

## Source behavior reported
1. studentaid.gov Data Center pages are JavaScript apps. File lists are available as page-content JSON at `<page>.json` (undocumented). Used with a clear failure if the layout changes. The file's own links are the only source of file URLs.
2. studentaid.gov over HTTP/2 intermittently failed for plain clients (`INTERNAL_ERROR`) during research; httpx worked in tests. Not reproduced in the server runs.
3. Composite scores are published about two years late and only as legacy `.xls`.
4. The CDR workbook declares ~1M rows but has ~4.6k; the parser stops at the first blank row.
5. studentaid.gov `robots.txt` has `Crawl-delay: 7`; the server paces to it.
6. FAC: the 2023 Test College A report flags `is_internal_control_material_weakness_disclosed: Yes` but has no rows in `findings`, and the same report says `is_internal_control_deficiency_disclosed: No`. Reported as returned, with a warning.
7. FAC: EIN `000000001` matches a real 2016 record, so "an obviously fake EIN returns nothing" is not safe to assume.

## Not verified / not built
- FAC requirement-code letters (`type_requirement`) are not labeled; no authoritative mapping was fetched.
- FAC rate-limit behavior past 1,000 requests/hour was not exercised.
- FAC for institutions with no EIN/UEI match was only checked with an unknown EIN (returns an empty list).
- Older and newer HCM/composite layouts than those above; the `.xlsx` variant of composite scores.
- `.mcpb` bundle, PyPI publishing, GitHub Actions: not run.
