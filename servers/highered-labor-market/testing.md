# Testing record: highered-labor-market

## Fixture tests (`pytest`, no network)
85 tests with in-memory upstreams in the real shapes: crosswalk workbook (including a NO MATCH row), BLS Table 1.2 (line items, a summary row, a broad group), O*NET CSVs (a suppressed rating, a supplemental task, a duplicate technology, a prompt-injection task), and Scorecard program JSON (suppressed earnings, an un-padded CIP code, an invalid credential level).
- **Crosswalk / BLS / O*NET / Scorecard parsers**: NO MATCH becomes an explicit null, never an occupation; BLS summary rows dropped; broad-group fallback flagged; suppressed O*NET ratings dropped; only core tasks and hot technologies kept; Scorecard codes padded and bad levels dropped.
- **Tools**: 6-digit and 4-digit mapping and the union of 6-digit codes; BLS thousands converted to people; skills from bulk files with the CC BY 4.0 citation and no key header; outcomes sorted by awards, suppression reported as one null with a reason, national medians kept under their own label; alignment returns ranges (no score/ratio/gap anywhere in the output), the disclosed education-match rule, a warning when no occupation matches the credential, broad BLS groups counted once, and degrades to supply, outcomes and occupations when the BLS contact is missing.
- **Cache**: second call makes no requests; stale copy served with a flag when BLS fails.
- **Security**: the contact address goes to `www.bls.gov` only (checked across every host the tools call), is attached per hop (a redirect from NCES to BLS gets it only at BLS; a redirect from BLS to another host is blocked and never carries it), never appears in a URL, body, output, tool description or error; malformed addresses (empty, no `@`, spaces, CRLF header injection, trailing newline, double `@`, oversized local part) are refused before any BLS request; disallowed host, non-HTTPS and size cap; bad or hostile workbooks and CSVs fail with a safe message; the Scorecard key is header-only; cache traversal and checksum tamper; tools are read-only with static descriptions.
- **Negative inputs** rejected before any network call: malformed, padded, injection-shaped and full-width-digit CIP, SOC and UNITID values; out-of-range credential, `top` and `limit`; wrong types.

## Milestone 5: state projections (Projections Central)
- **Mock** serves the API's real row shape (string numbers, unpadded `STFIPS`, a ' United States' area with FIPS 0) and its real failure shape (HTTP 404 'No results found.').
- **Tests**: row validation (bad SOC, SOC with a trailing newline, bad FIPS, bad years, unparseable numbers become null, non-https or whitespace URLs dropped); one request returns the state and the United States for the occupation and its broad-group code (`/25+0/29-1141+29-1140`); caching per area and occupation (second call and other states reuse it; expired entries are refetched; a checksum-tampered file is ignored); stale fallback on a 503; broad-group fallback flagged; missing states, short-term gaps and unknown occupations are nulls with reasons; differing state and US periods warned; **rows for areas or occupations not requested are dropped and counted** (checked by mutation: removing the filter fails the test); extra pages and non-JSON shapes fail safely; errors carry no URL or contact address; the BLS contact address is never sent to this host; batching (100 codes per request) joins codes with '+'; alignment with `state` returns the state table, same-source US column and totals, keeps BLS national separate, works without the BLS contact, and counts a broad state group once.
- **Inputs rejected before any request**: unknown, lowercase and spelled-out states; `25+0`; a SOC joined with `+` or `/all`; full-width digits and trailing newlines; unknown horizon.
- **Live (2026-10-31)**: Massachusetts RN 91,850 to 94,850 (2024 to 2034), 4,930 openings a year vs 189,100 for the United States in the same source; Massachusetts reports home health aides only as broad group 31-1120; Alabama has no short-term RN row (15 areas publish one); Test College A's 51.38 associate nursing program maps to six occupations with 8,000 state openings a year vs 292,500 for the United States (same source) and 283,800 BLS national (2025-35), all clearly separated. A stdio session through the Desktop configuration listed the new tool and returned Texas RN data.

## Live (`HIGHERED_LIVE=1`)
Passed 2026-10-31 (9 s, cold cache): 51.3801 maps to nursing instructors and registered nurses; BLS 2025-35 registered nurses show 180,800 annual openings and a bachelor's typical entry education; O*NET 31.0 skills for 29-1141; Test College A programs; Test College A 51.38 associate alignment. Stdio session over `uvx --from <local path> highered-labor-market` listed the five tools, returned BLS data, and rejected a full-width-digit CIP.

## Found while testing
- Python's `$` matches before a trailing newline, so `a@example.org\n` passed the contact-address pattern (a header-injection shape). All `re.compile` patterns in all four servers now end with `\Z`; the contact check has a regression case and the institutions server a trailing-newline case. Pydantic input patterns were already strict.

## Source behavior reported (not worked around)
1. `www.bls.gov` and `download.bls.gov` return 403 to clients without a contact email in the User-Agent. With one, `robots.txt`, the projections workbook and the LABSTAT listing return 200 (tested 2026-10-31 with an address the owner supplied for testing). BLS's own wording of this requirement was not found; confirm with BLS (a draft message is in PLAN.md).
2. Urban's IPEDS completions endpoint uses award-level codes (4, 7, 8, 9, 22, 23, 30, 31 in 2023) that do not match older IPEDS coding, and no codebook was reachable. The first stage therefore uses Scorecard's labeled credential levels and award counts instead.
3. BLS reports some occupations only as broad groups (for example 31-1120 for 31-1121 and 31-1122).
4. Scorecard marks suppressed values "PS"; the API returns them as null.

## Source behavior reported (Milestone 5)
5. Projections Central fails closed on unknown filters (empty rows or HTTP 404 'No results found.'), unlike NIH RePORTER. Rows are still validated against the request.
6. Only 15 areas publish short-term (2-year) projections for registered nurses; long-term covers 55 areas.
7. State agencies sometimes report an occupation only as a broad group (Massachusetts: 31-1120 for 31-1121 and 31-1122).

## Source behavior reported (Milestone 5)
5. Projections Central fails closed on unknown filters (empty rows or HTTP 404 'No results found.'), unlike NIH RePORTER. Rows are still validated against the request.
6. Only 15 areas publish short-term (2-year) projections for registered nurses; long-term covers 55 areas.
7. State agencies sometimes report an occupation only as a broad group (Massachusetts: 31-1120 for 31-1121 and 31-1122).

## Not verified / not built
- Which of Scorecard's two award-count periods is newer.
- Debt and 3-year earnings fields (not requested), Census PSEO, sub-state (regional) projections, job postings (paid). Projections Central has no separate terms page that I could find; its in-app disclaimer was read and is returned in responses.
- BLS file layout beyond Table 1.2, and layouts before the 2025-35 release.
- `.mcpb` bundle, PyPI publishing, CI run for this server, Windows.
