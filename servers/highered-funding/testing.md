# Testing record: highered-funding

## Fixture tests (`pytest`, no network)
64 tests, using in-memory upstreams that mimic each source's real shape (a HERD zip with a short-form file, an imputed value and a UNITID-less institution; SHEEO and WICHE workbooks; NSF, NIH and Grants.gov JSON including person fields, rows from other organizations, bad ids and a prompt-injection title).
- **HERD**: thousands converted to dollars; standard and short-form institutions found; imputed flagged; a source line not reported is null, not zero; absent institution is a null with the $150,000 reason; UNITID-less institutions listed unjoined only when `state` is given and never name-joined; discovery ignores traversal links and other hosts; non-zip, wrong member, wrong columns, decompressed-size cap while streaming, oversized download; cache reuse and stale fallback.
- **SHEEO / WICHE**: discovery takes the newest fiscal year and only the right host; table, units, citation and license present; missing years are nulls; unknown state, bad window, unknown series; parser guards.
- **NSF**: exact UEI request; two-page fetch with distinct ids; person fields and abstracts never appear in output; dates converted and invalid calendar dates rejected; truncation and ordering warnings; bad award ids dropped.
- **NIH**: only rows whose own UEI matches are kept (other organizations and rows with no UEI dropped); request body has no `org_ueis`; "nothing verifies" and "name matched far more than examined" cases reported; name required, NSF still answers without it.
- **Grants.gov**: labeled as opportunities not awards; eligibility and agency filters in the body; JWT token from the response not returned; bad id dropped.
- **Security**: disallowed host for GET and POST; POST refused for every host except the two search APIs (nothing leaves the process); redirects checked per hop and never followed on POST; response size cap; errors carry no query text or URL; cache name traversal and checksum tamper; tools are read-only with static descriptions.
- **Negative inputs** rejected before any network call: malformed, oversized and full-width-digit UNITIDs; lowercase, short, long, padded and operator-laden UEIs; out-of-range limits, years, rows; bad states, sectors, enums; bad dates; injection-shaped names and agencies.

## Live (`HIGHERED_LIVE=1 pytest -m live`)
Passed 2026-10-31 (28 s cold): Penn State HERD rows; Test College A absent from HERD with a reason; Massachusetts SHEEO and WICHE series; Penn State NSF (6,526 awards) and NIH (181 verified FY2025 projects); Grants.gov opportunities. Stdio session over `uvx --from <local path> highered-funding` listed the five tools, returned SHEEO data, and rejected a full-width-digit UNITID.

## Found while testing
- Full-width digits satisfied `\d` patterns in pydantic and `re`. Fixed in all three servers by using `[0-9]`; regression cases added to each.

## Source behavior reported (not worked around)
1. NSF ignores `printFields` and returns PI, co-PI and program-officer contact details in every record; `awardeeName` is a keyword search that also matches abstracts; boolean operators inside parameter values are interpreted by the API.
2. NIH RePORTER silently ignores unknown criteria such as `org_ueis` and then returns the whole database (2.98 M projects for a junk UEI). The server never relies on it and verifies each row's UEI.
3. HERD publishes short-form institutions in a separate file (FY2012+), and 32 of 681 FY2024 standard-form institutions have no UNITID.
4. SHEEO and WICHE file paths contain dated folders; links are discovered from the pages.
5. WICHE data are CC BY-NC-SA 4.0.

## Not verified / not built
- HERD for years before FY2015 was not parsed (same header seen for 2015, 2020, 2023, 2024 only). Default window is the latest 3 years.
- Grants.gov detail-page URL pattern (`/search-results-detail/<id>`) was not fetched; ids come from the API.
- SHEEO institution-level data (SHEF Expansion) was not located; not planned.
- No WICHE regional or national series (state rows only).
- `.mcpb` bundle, PyPI publishing, GitHub Actions run for this server, Windows: not run.
