# Testing record: highered-accreditation v0.1.0

## Automated (fixture-based) — `PYTHONPATH=src uv run --no-sync pytest`
Result on 2026-10-31: **121 passed, 1 skipped** (opt-in live test).
Fixtures are synthetic zips built in `tests/conftest.py` with the same three CSVs and column names as the real DAPIP download, including a byte-order mark. They carry sentinel contact details so that personal-data leaks are detectable. No real DAPIP file is committed.

Covers: the UNITID to institution to records and actions join; an institution with two UNITIDs; branch and additional-location rows ignored; `current` computed from the end date (ended today, ended earlier, scheduled in the future, "Denied Accreditation"); scope filters including state agencies; actions newest first with undated rows last; counts by category over everything that matched, not just the returned page; `since_year` and `limit`; unknown wording reported as `unclassified`; impossible dates become null; unmatched UNITID gives a null with a reason; upstream text kept as data, control characters removed and length capped; fresh cache makes no request, 29 versus 31 days, stale fallback with a warning, corrupt cache refetched, a garbage download never cached; sources carry the file checksum; the only request ever sent is the fixed POST.

Negative tests: malformed UNITIDs (5 and 7 digits, letters, full-width digits, trailing newline, leading space, traversal, injection-style) and bad `scope`, `since_year` and `limit` values rejected before any network call; zip with an extra, traversal, absolute-path, nested or look-alike member; missing member; duplicate member; zip bomb (about 20 MB of zeros in under 100 KB); oversized member; a member read that asks for a bounded amount; changed column layout; malformed ids in rows; non-zip download; POST to any URL other than the download URL; plain http, other schemes, credentials in the URL, ports, look-alike hosts; a redirect on the POST not followed and nothing contacted but `ope.ed.gov`; response over the size cap; retries bounded; transport errors that carry a local path are not echoed; cache names with `..`, newlines, uppercase, slashes, `.tmp`.

Mutation checks (a safety check was broken on purpose and a test had to fail): member-name allowlist, compression-ratio limit, location filter, personal-data leak, `current` computed from the end date, bounded member read, control-character removal, POST URL allowlist, redirect refusal, https-only, `..` in cache names, cache checksum, branch records dropped. Four of the first thirteen survived (location filter, bounded read, https-only and `..` in cache names had no test that could tell); tests were added and all four are now caught.

## Change after the three-college validation (2026-10-31)
Found by reading Test University C's output: an ended nursing record from a previous accreditor (ended 2013, no recorded action) was listed in `not_current_programs` by program name only, which could be read as a lost accreditation. Each record now carries `last_action`, and `not_current_programs` returns the agency, end date, status text and `last_action`. Two tests added (newest action wins; null when none), and a mutation that picks the oldest action is caught. 122 passed, 1 skipped.

## Live (opt-in) — `HIGHERED_LIVE=1 pytest -m live`
Run 2026-10-31: **1 passed** (8 s cold, one 3.7 MB download).

Verified live against the real file (current to 2026-10-29; 10,361 institution rows, 7,428 matched to a UNITID, 2,920 with no UNITID):
- Test Community College A (UNITID 999001, DAPIP id 990001, OPE ID 09990100): New England Commission of Higher Education is current (accredited 1981); the associate nursing record (ended 2019-12-31) and radiologic technology record (ended 2022-08-23) still say "Accredited" in DAPIP and are reported as not current.
- Test College A actions as recorded: nursing show cause 2018-09-12, then loss of accreditation (voluntary withdrawal) 2019-12-31; radiologic technology probation 2022-01-18, then loss of accreditation 2022-08-23; institutional heightened monitoring or focused review 2023-03-03 with the agency's justification text; renewals 2015, 2020, 2021 and 2025. These match the raw CSV rows read during research.
- End-to-end MCP stdio session via `uvx --from <local path> highered-accreditation`: tools/list, both tools, and a rejected malformed UNITID.

## Source behavior reported
1. The download is a POST (the site's Download button); a GET returns HTTP 405.
2. `robots.txt` for `ope.ed.gov` could not be read: it redirects to an ed.gov page, and a plain request got a firewall block page. No terms page was found. The owner approved proceeding.
3. The status text is not updated when a record ends (27,472 ended records still say "Accredited"). Handled by computing `current`.
4. 2,279 agency names contain "?" where a dash was lost, and some justification text does too. Returned as given.
5. 35,784 actions give "Other - Provide unlisted or multiple justifications"; the free-text detail is present on about as many.
6. Branch records (9-digit DAPIP ids) hold 36,533 of the 65,446 accreditation records and are not returned.
7. The institution file includes administrator names, emails and phones; they are dropped at parse time.

## Not verified / not built
- Windows, `.mcpb` bundle, PyPI publishing.
- The category rules were written from the distinct action wordings in the file on 2026-10-31; wording added later is reported as `unclassified`.
- State board actions outside the seven state agencies DAPIP carries: no national feed exists, so none are available.
- Whether a record's `review_date` is the next scheduled review is DAPIP's field name; the tool does not interpret it.
