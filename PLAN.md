# PLAN: highered-mcps

Status: **research complete, awaiting your review. No server code written.** Evidence is in `docs/sources.md`.

## Repo layout (mirrors 1102tools where it fits)

```
highered-mcps/
  LICENSE (MIT)  README.md  CONTRIBUTING.md  SECURITY.md  .gitignore  .env.example
  docs/  sources.md  threat-model.md  using-with-1102tools.md
  .github/  dependabot.yml  workflows/ test.yml  publish-pypi.yml  mcpb.yml  secrets-scan.yml
  servers/
    highered-institutions/
      pyproject.toml  uv.lock  README.md  testing.md  SKILL.md  manifest.json (mcpb)
      src/highered_institutions/  server.py  models.py  http.py  crosswalk.py  sources/{urban,scorecard,propublica}.py
      tests/  fixtures/  test_*.py
    highered-risk/      (same shape)
    highered-funding/   (same shape)
```

Differences from 1102tools: no `shared/` package (they have one; I'll duplicate the small HTTP guard in each server first and only extract after the third copy), no Dockerfile/smithery/hosted-service machinery, Python 3.11+.

## Key architecture decisions

- **One `http.py` per server** (~80 lines): HTTPS-only, host allowlist checked before every request and on every redirect hop (redirects handled manually, `follow_redirects=False`), timeouts, streamed response size cap, 3 retries with backoff on 429/5xx, `params=` only, key scrubbed from errors.
- **One `cache.py` per bulk-source server**: resolve path, require it to be inside the cache dir, write SHA-256 and as-of in a sidecar JSON, size cap. No locking library, atomic rename.
- **Response envelope** on every tool: `{source, source_url, as_of, retrieved_at, data, nulls: [{field, reason}], warnings}`; series/tables as `{columns, rows}`.
- **Crosswalk is built on demand from the Urban IPEDS directory** (one record already holds UNITID, OPEID, EIN, UEIs, domain, system name, Carnegie). Scorecard adds OPEID6 grouping. No persisted crosswalk database.
- **`resolve_institution` match ladder**: exact identifier -> `exact`; domain -> `exact_domain`; name -> `name_match` with score. Multiple hits at similar score or one OPEID6 spanning several UNITIDs -> return all candidates with `ambiguous: true`, never pick. Any join not by identifier carries `match_basis: "fuzzy_name_state"`.
- **Tools, Milestone 1**: `resolve_institution`, `search_institutions` (filters by state, control, Carnegie, size; enum-validated), `get_institution_profile`, `get_enrollment_trend`, `compare_peers`. `compare_peers` defines peers deterministically (same Carnegie 2025 basic class + same control, nearest on latest total enrollment; the rule is returned in the response), no ML.

## Dependencies (each justified)

| Dependency | Why |
|---|---|
| `mcp` (official SDK, FastMCP) | required; pin to the range 1102tools uses (`>=2.0.0,<3`), **to be confirmed against PyPI at build time** |
| `httpx` | required HTTP client with params, timeouts, no auto-redirect control |
| `pydantic` | required input validation |
| `defusedxml` | only if an XML source appears (none so far; **not added in M1**) |
| `openpyxl` (read-only) | M2/M3 only, for XLSX bulk files (FSA, WICHE); not added in M1 |
| dev: `pytest`, `pytest-httpx`, `respx` alternative not needed, `pip-audit`, `ruff` | tests, fixture mocking, audit, lint |

Not adding: `platformdirs` and `filelock` (1102tools uses them). I'll use `Path.home()/.cache/highered-mcps` overridable by `HIGHERED_MCPS_CACHE`, and atomic rename instead of locks. Revisit if Windows paths cause trouble.

## Milestones

### M1 highered-institutions
Deliver: the server, tests incl. negative tests, README (allowlist, injection risk, key setup), testing.md, SKILL.md, `.mcpb` manifest, CI workflows, SECURITY.md, threat-model.md, root docs, lockfile, then a local git commit.
Hosts allowed: `educationdata.urban.org`, `api.data.gov`, `projects.propublica.org` (if kept).
Needs: free Scorecard key (`COLLEGE_SCORECARD_API_KEY`).
Deferred: Carnegie ACE file download (codes come from Urban; labels null until documented), UEI-sourced match from SAM.gov, IRS 990 bulk.
Done check: "Show the enrollment trend for [institution] and its closest peers."

### M2 highered-risk
Blocked until FSA file URLs are found (see sources.md section 5) and a FAC key exists. Tools `get_fsa_status`, `get_audit_findings`. Hosts: `studentaid.gov` (and possibly `fsapartners.ed.gov`), `api.fac.gov`. Bulk download with checksum and as-of surfaced. Deferred: accreditor actions, EMMA.

### M3 highered-funding
Blocked on HERD codebook check, SHEEO/WICHE file URLs. Tools `get_research_spend`, `search_grant_awards`, `get_state_funding`, `get_enrollment_projection`. Hosts: `ncses.nsf.gov`, `api.nsf.gov`, `api.reporter.nih.gov`, `api.grants.gov`, `shef.sheeo.org`, `www.wiche.edu`. `get_state_funding` returns state/sector (and institution-level only for 2008-2022 via SHEF Expansion if confirmed). `get_enrollment_projection` is state-level and says so in every response.

## Assumptions

1. Harvard-style test institution is a placeholder; you left `[institution]` blank. I'll use a configurable fixture set (Harvard, a multi-campus system such as Penn State, a community college) unless you name one.
2. Local-path `uvx --from ./servers/highered-institutions highered-institutions` is what "starts via uvx" means.
3. Urban API stays available and stable (it is a third-party non-government host; no SLA).
4. Fixtures are recorded from live responses after scrubbing; keys never appear because Urban and ProPublica need none and Scorecard keys go in a header-free query param that is stripped.
5. Scorecard key is passed as `api_key` query param (its documented method). That param would appear in httpx URLs, so error handling and logging will redact it.

## Open questions (need your answer before M1 code)

1. **Urban `robots.txt` `Disallow: /api/`**: proceed with 1 req/sec and a documented note, switch to bulk CSV, or contact Urban first? (sources.md, decision 1)
2. **ProPublica CC BY-NC-ND**: drop, make optional/non-commercial, or replace with IRS 990 bulk? I recommend dropping it from the crosswalk and revisiting later. (decision 2)
3. **Grants.gov**: it lists opportunities, not awards. Keep as an "open opportunities" filter, or drop? (M3, not urgent)
4. **Name of the test institution** for done-criteria.
5. **Scorecard API key**: please register at api.data.gov/signup and export `COLLEGE_SCORECARD_API_KEY`. FAC key needed before M2.
6. **Repo naming/author** for `pyproject` metadata and PyPI project names (`highered-institutions` etc.). Reserving names on PyPI is a publish-adjacent step I will not do without your OK.
7. Whether to `git init` the monorepo now (local only, no remote).

## Risks

- Third-party data shifts under us (Urban field names, Scorecard null handling). Mitigation: contract tests on recorded fixtures plus opt-in live tests, and report diffs rather than patch silently.
- UEI coverage in IPEDS may be sparse; UEI resolution may return few matches. Will measure on a sample and document in testing.md.
- FSA files hidden behind a JS shell may require a browser to locate; stable direct URLs might not exist.

## Decisions log (2026-10-31)

- ProPublica: **kept** for EIN confirmation and 990 financial summaries, per owner. Constraints from its Data Terms (read today): no republishing the raw data in bulk, no resale, no charging to view it, no altering data except to correct, cite ProPublica. Design: per-EIN pass-through only, original fields returned unmodified (normalized EIN added alongside), no ProPublica caching, no officer/employee fields, attribution in every response.
- Grants.gov: **kept** as an open-funding-opportunities search (M3), labeled as opportunities, not awards.
- Test institution: **Test Community College A**, UNITID 999001, OPEID 09990100, EIN 999000001, system "Massachusetts Community Colleges".
- Scorecard key: in gitignored `.env` (never committed). Verified live: 1000/hr limit.
- Git: local repo only; remote set up later by owner.
- Urban fetch strategy: **pending owner decision** (see below).

## Measured today
- Full Urban directory for one year is a single response: 6,072 institutions, 14 MB, 0.6 s. Name filters (`inst_name=`) are silently ignored server-side, so name search must filter locally from that pull.
- `ueis` populated for 5,537 of 6,072 (91%); `ein` for all 6,072.
- Test College A fall 2023 total enrollment: 1,711 (filter ftpt/sex/race/level all = 99).

## Milestone 1 note (2026-10-31)
Built: `servers/highered-institutions` (5 tools), tests, docs, CI files, mcpb manifest.
Deviations: the SDK is `mcp` 2.3.0, where FastMCP is renamed `MCPServer`. No `platformdirs`/`filelock` (plain env/home path, atomic rename). Dependencies: mcp, httpx, pydantic only.
Deferred: NCES/IPEDS fallback source (only stale-cache fallback exists), Carnegie labels, ACE Carnegie file, SAM.gov-based UEI match, `.mcpb` and PyPI publish unverified, Windows untested.
Reported upstream behavior: Urban `Disallow: /api/`; Urban HTTP 500 for unpublished years; Urban ignores name filters.

## Milestone 2 note (2026-10-31): complete
Built: `servers/highered-risk` with `get_fsa_status(opeid)` (HCM, composite scores, cohort default rates), 23 tests, live run, uvx session, docs.
New dependencies: `openpyxl` (FSA .xlsx files, read-only mode) and `xlrd` (composite scores exist only as legacy .xls). Dev-only: `xlwt` (builds the .xls test fixture).
Design choice: the tool takes an 8-digit OPEID (resolve it with highered-institutions) instead of a UNITID, so the servers stay independent.
Part 2 (after FAC key): `get_audit_findings(ein|uei, years)` over `general`, `findings`, `federal_awards`; explicit field list excludes contact PII; no narratives. Deferred as planned: accreditor actions, EMMA.
Open: composite scores lag about two years and omit public institutions; confirm that is acceptable for the "Title IV financial responsibility score" question.

## Decisions log addendum (2026-10-31, after M2)
- ProPublica **dropped** from highered-institutions (owner decision): source module, allowlist host, `include_990` parameter, fixtures and docs removed. 990 data is no longer part of the profile.
- Urban stays paced at 1 request/second (owner-approved) with a 90-day cache.

## Milestone 3 research outcome (2026-10-31): sources verified, build not started

Composite scores: no newer or broader FSA source exists; IPEDS finance (FY2023) covers publics but is the same period. See docs/sources.md.

Proposed design (pending owner answers below):
- `get_research_spend(unitid)`: HERD. Per-year zip (7.5 MB), stream-parse the CSV (49 MB), keep only the `01.*` rows for the institutions, cache a compact per-year JSON with the zip's SHA-256. Thousands of dollars converted and labeled. 32 institutions lack a UNITID in HERD; for those the tool returns a null and lists same-state unmatched HERD entries as unjoined candidates, never a name join.
- `search_grant_awards(...)`: three sources with different identity strength, labeled per result. NSF: exact by UEI, fields projected to a safe list (no person fields). NIH: name query then UEI verification. Grants.gov: opportunities only, filtered by eligibility, no institution identity. Guard gains a POST method restricted to these search endpoints.
- `get_state_funding(state, ...)`: SHEEO report and sector data, state level, citation in every response.
- `get_enrollment_projection(state, ...)`: WICHE, state level, license-dependent.

Decisions needed from owner:
1. WICHE license (CC BY-NC-SA 4.0): include with attribution and a warning, or skip `get_enrollment_projection`?
2. Add an IPEDS-finance snapshot tool for publics (raw reported figures, no composite)?
3. NIH matching by name plus UEI verification: acceptable?

## Milestone 3 note (2026-10-31): built
Owner decisions: include WICHE with attribution and license warning; build the IPEDS finance snapshot; keep NIH name-plus-UEI matching and gather community feedback.
Built: `servers/highered-funding` with `get_research_spend`, `search_grant_awards` (NSF + NIH), `search_funding_opportunities` (Grants.gov, a separate tool so awards and opportunities are never mixed; deviation: one more tool than the brief), `get_state_funding`, `get_enrollment_projection`. 64 tests, live run, stdio session. `get_financial_snapshot` added to highered-institutions (Urban finance endpoint, reported as filed, no scoring).
New dependency: `openpyxl` (SHEEO and WICHE workbooks). Guard gains POST, limited to the NIH and Grants.gov hosts.
Found and fixed: Unicode digits passed `\d` validation in all three servers (now `[0-9]` with regression tests).
Deviations from the original plan: SHEEO institution-level data (SHEF Expansion) not found, so `get_state_funding` is state-level only; HERD short-form institutions are included (separate file); HERD join is by UNITID with 32 of 681 FY2024 institutions unjoinable.
Not done: NCES/IPEDS backup for Urban; Carnegie labels; `.mcpb`, PyPI publishing, new-server CI run, Windows.

## Milestone 4 plan (2026-10-31): `highered-labor-market` (proposal for owner review, no code written)

Goal: help institutions look at aligning programs with labor-market demand, using only free public data. Audience assumption (owner has not answered): community-college workforce and program review first, but nothing community-college specific. Every number is labeled with its level (national, state, institution) and source; no composite "alignment score".

### Data chain (all verified in docs/sources.md unless marked)
program (CIP) -> occupations (NCES/BLS CIP-SOC crosswalk) -> demand (BLS Employment Projections 2025-35) and skills (O*NET 31.0) ; supply (IPEDS completions via Urban) ; outcomes (College Scorecard field-of-study).

### Tools (proposed)
1. `map_program_to_occupations(cip)`: crosswalk rows for a 6-digit (or 4-digit prefix) CIP. NO MATCH becomes a null with reason. States that the crosswalk is not empirical and lists every mapped occupation.
2. `get_occupation_outlook(soc)`: BLS projections: employment 2025 and 2035, change, annual openings (growth plus replacement), typical entry education, experience, training. National only. **Blocked on BLS access, see below.**
3. `get_occupation_skills(soc)`: O*NET skills, tasks, technology skills, with the required O*NET attribution and database version.
4. `get_program_outcomes(unitid, cip4?, credential?)`: Scorecard field-of-study earnings, debt, counts. Suppressed institution values are nulls with the suppression reason; national comparison values are returned under their own label.
5. `get_program_supply(unitid, cip?, award_level?)`: latest IPEDS completions for the institution by CIP and award level.
6. `get_program_alignment(unitid, cip6, award_level)`: joins 1, 2, 4 and 5 into a table, not a score: the institution's completions beside, for each mapped occupation, national projected annual openings and typical entry education, plus a deterministic filter (disclosed in the response) that marks occupations whose typical entry education matches the award level. Totals are shown as a range across the filter (all mapped vs education-matched), never one ratio.

Honest limits the responses must state: national openings are not regional demand; completions are not graduates who stay in the region; BLS entry education is a classification, not a requirement; the crosswalk is many-to-many (max 180 occupations per CIP); Scorecard programs use 4-digit CIP while completions use 6-digit; projections lag and cannot see current postings.

### Stage 2 (after 4a review)
Census PSEO earnings and industry flows (needs a free Census key or verified raw-file names; partner-institution coverage only); state or regional projections (Projections Central or state labor agencies, unverified; 50 sources, so start with a few states); CareerOneStop (unverified).

### Out of scope
Job-postings data (Lightcast, Indeed and similar are paid or gated); NACE and CCRC data tools (reasons in docs/sources.md); employer surveys; any hosted data. Wage benchmarks stay with the 1102tools BLS OEWS server (document the combined use in docs/using-with-1102tools.md rather than duplicating).

### Dependencies and keys
No new Python dependency expected (`openpyxl` already used; O*NET CSV via stdlib `csv`). New hosts to allowlist: `www.bls.gov` (if access is resolved), `www.onetcenter.org`, `nces.ed.gov`, plus existing Urban and api.data.gov. Keys: Scorecard (already). **O*NET API key is not needed for 4a** because skills and tasks come from the CC BY 4.0 bulk files; it is only needed if we use Web Services (for example its job-outlook endpoint, contents unverified). Census key only for stage 2.

### Decisions needed from the owner
1. **BLS access.** `www.bls.gov` returns 403 to our client. Options: (a) add a required-contact setting (for example `HIGHERED_MCPS_CONTACT`, an email each user supplies, sent only to BLS in the User-Agent) if BLS confirms that is its policy; the owner would choose a contact address to test with. (b) Ask BLS (their data-help contact) how automated clients should fetch the projections file. (c) Fall back to O*NET Web Services job-outlook data if it carries the BLS projections (unverified). Recommendation: (b) and (a) together; I will not spoof a browser or use anyone's email without being told.
2. **Audience** (see above).
3. **O*NET key**: owner is comfortable registering; recommendation is to register now but build 4a on the bulk files first.
4. **Order of build**: crosswalk and O*NET and outcomes and supply first (all verified), outlook and the combined alignment tool after BLS access is settled.

### Verify before building
Urban award-level codes and CIP encoding; Scorecard field-of-study field names for credential levels and the exact suppression markers; crosswalk handling of CIP codes with trailing letters or older CIP editions in completions; O*NET-SOC (8-digit) to SOC (6-digit) mapping; BLS file layout once reachable.

## Milestone 4 note (2026-10-31): first stage built (`highered-labor-market`)
Owner decisions: build on the O*NET bulk database (no key); add a setting where each user supplies their own contact email, sent only to BLS; owner supplied a test address for BLS (kept only in the gitignored `.env`).
Built: `map_program_to_occupations`, `get_occupation_outlook`, `get_occupation_skills`, `get_program_outcomes`, `get_program_alignment` (5 tools, 58 tests, live run, stdio session).
Changes from the proposal: supply now comes from Scorecard's award counts (labeled credential levels) instead of Urban completions, because Urban's award-level codes could not be decoded; there is no separate `get_program_supply` tool. BLS access is solved by the contact email (`HIGHERED_MCPS_CONTACT`).
Found and fixed in all servers: `$` in Python patterns matches before a trailing newline; patterns now end with `\Z`.
Still open: ask BLS to confirm its automated-access policy (draft below); PSEO (needs a free Census key or verified raw-file names); state or regional projections; Scorecard debt and 3-year earnings; which award-count period is newer.

Draft message to BLS (owner to send if desired): "We maintain an open-source, read-only tool (github.com/bsayres/highered-mcps, MIT) that lets college staff look up the national Employment Projections workbook (https://www.bls.gov/emp/ind-occ-matrix/occupation.xlsx) on demand, about once a quarter per user, at no more than 1 request per second, with the user's own contact email in the User-Agent. Is that an acceptable way to fetch it, and is there a preferred format or endpoint for automated clients?"

## Review fixes (2026-10-31): done after the owner's Test College A provost-brief test
Fixed: (1) filing timeline and nine-month rule in `get_audit_findings`; (2) multi-year finance history and revenue components, no netting of capital appropriations (components do not reconcile in every year); (3) `compare_peers` scope same_state and same_system; (4) SKILL rules (no verdicts from one year, no comparing national openings to one college's awards, quote the timeline, sources with as-of dates); (5) FAC-dictionary labels for requirement codes. An earlier assumption that `modified_opinion` meant a compliance opinion was wrong: FAC's definition does not say which opinion.

## Milestone 5 plan: state occupation projections (BUILT, see note below)
Answer to "needed for every state?": no. Projections Central serves every state, DC and three territories through one documented REST API in one format, queried on demand for the state the user asks about. There is nothing to build per state. Regional (sub-state) projections are published by each state separately and are not in this API; they are out of scope unless owners want selected states later.
Proposed:
- `get_state_occupation_outlook(state, soc)`: base and projected employment, change, average annual openings, base and projection years (returned per row), the state agency's URL, and the same occupation's United States row from the same source and vintage for a like-for-like comparison. Null with a reason when a state has not submitted the occupation.
- `get_program_alignment(..., state=None)`: with a state, add each mapped occupation's state openings beside the national BLS figures, labeled by level and vintage (state 2024-34 is not the same period as BLS national 2025-35; never combine them).
- Per-request pacing 1 s, GET only, response caching per (state, SOC), strict inputs (state enum, SOC pattern), `[0-9]` and `\Z` patterns, host allowlist `public.projectionscentral.org`.
Verify before building: the terms of use for public.projectionscentral.org (none read yet); whether short-term projections are worth including; how blanks look for states that have not submitted; paging for `all` with many SOC codes (100 rows per page).
Hosts and keys: no key, no contact email. A User-Agent naming the project is polite; BLS's contact-email requirement does not apply to this host (not tested for one).

## Milestone 5 note (2026-10-31): built
Built in `highered-labor-market`: `get_state_occupation_outlook(state, soc, horizon)` and a `state` option on `get_program_alignment`. 85 tests (27 new for projections), live run, stdio session through the Desktop config. Terms check done: no restrictions found, disclaimer returned in responses. Deviations from the plan: short-term (2-year) projections included as `horizon='short'` (coverage is partial and the tool says so); the single-occupation tool fetches the state and the nation in one request and the alignment option batches up to 100 codes per request; broad-group codes are requested alongside detailed ones. A safety review by mutation showed the "drop unrequested rows" filter was invisible to the first test; the dropped-row count is now returned and asserted.
Still open: sub-state (regional) projections (each state publishes its own; not in this API), Census PSEO, accreditation and state or board actions (the other gap in the Test College A brief), BLS policy confirmation (draft message above), `.mcpb` bundles, PyPI publishing, Windows.

## Milestone 6 plan: accreditation (proposal for owner review, no code written)
Research done 2026-10-31 against the live source. This is the "accreditation and state or board actions" gap in the Test College A provost brief.

### Source (verified)
- **DAPIP**, the Department of Education's Database of Accredited Postsecondary Institutions and Programs. The site's own Download button POSTs `{"CSVChecked":true,"ExcelChecked":false}` to `https://ope.ed.gov/dapip/api/downloadFiles/accreditationDataFiles` and gets `DAPIPData.zip` (3.7 MB; 48.5 MB unpacked) with exactly three CSVs: `InstitutionCampus.csv` (OPE ID, IPEDS UNITID, name), `AccreditationRecords.csv` (agency, program, status, dates) and `AccreditationActions.csv` (90,065 dated actions with a justification code). No key. The file is generated on request and was current to 2026-10-29 when fetched.
- Join: UNITID to DapipId (Test College A: DapipId 990001, OPE ID 09990100), then DapipId to records and actions.
- Scorecard also has the institutional accreditor name (`school.accreditor`; Test College A: NECHE). DAPIP is the richer source, so Scorecard is only a cross-check.

### What the live data shows for Test College A (as DAPIP records it; not confirmed with the agencies)
- Institutional: New England Commission of Higher Education, accredited since 1981, "Heightened Monitoring or Focused Review" recorded 2023-03-03, renewal recorded 2025-09-25.
- Nursing (associate degree, ACEN): "Show Cause" 2018-09-12, then "Voluntary Withdrawal" 2019-12-31. The record's end date is 2019-12-31, but its status field still says "Accredited".
- Radiologic technology (JRCERT): probation 2022-01-18, "Loss of Accreditation: Other" 2022-08-23; record end date 2022-08-23, status still "Accredited".

### Data quirks the tools must handle
- `AccreditationStatus` is never updated when a record ends (27,472 records have an end date and still say "Accredited"). Current status must be computed from the end date, and the tool must say so.
- 2,920 institution rows have no UNITID (they cannot be joined to IPEDS); 19 rows list two UNITIDs in one field. A UNITID with no match returns a null with a reason, never a guess.
- 2,279 agency names contain a "?" where a dash was lost, with a "Formerly:" suffix. Shown as given (no rewriting) and documented.
- Justification is "Other - Provide unlisted or multiple justifications" on 35,784 actions: many actions have no stated reason, and the tool says "no reason given in DAPIP" rather than implying none exists.
- `InstitutionCampus.csv` carries administrator names, emails and phone numbers. These are dropped when the file is parsed and never cached or returned (personal-data rule); a test asserts no such field appears anywhere.
- Locations and branches ("Additional Location", "Site") are not returned; only the institution row matching the UNITID.

### Tools (proposed, added to `highered-risk`, which already holds the compliance signals)
1. `get_accreditation_status(unitid)`: institutional accreditor(s) and every programmatic accreditor on file, each with first accredited date, agency review date, end date, and `current` computed from the end date.
2. `get_accreditation_actions(unitid, since_year=None, scope='all'|'institutional'|'program')`: the dated actions, each with the agency's words verbatim, its justification, and a fixed documented `category` (adverse, monitoring, routine, substantive_change, other; unknown wording is `unclassified`). Newest first, capped. No score, no verdict, no "distress" label.
Both carry source, source_url, as_of (the latest action date in the file), retrieved_at.

### Build rules
- Allowlist adds `ope.ed.gov`; the Guard's POST is limited to that host and this one path; fixed body, not user-controlled. The zip is handled in memory only: exact member-name allowlist, declared and streamed size caps, compression-ratio limit, nothing extracted to disk, never executed. The cache holds a compact JSON of only the joined, projected rows (no admin fields), with checksum and as-of, written atomically under the cache dir.
- Refresh: 30 days (actions are added daily; one request a month per user is tiny). Stale cache is served with a warning if the refresh fails.
- Strict input: UNITID `[0-9]{6}`, enums for scope; negative tests as in the other servers (bad IDs, oversize zip, unexpected member name, path-traversal member name, zip bomb ratio, redirect to another host, disallowed host).
- README prompt-injection note: agency and justification text is upstream text, treated as data.

### Not covered (stated in the tools and SKILL)
State board and state approval actions (for example the Massachusetts nursing board's program approvals). DAPIP lists some state approval agencies as accreditors, but there is no single national feed for board actions; each state publishes separately. Agencies' own sites (NECHE's institution pages, ACEN's search) hold more detail and are not scraped (crawlers are out of scope); the tools link to them. Also not covered: Test College A-style program closures that the agency never reported to the Department.

### Decisions needed from the owner
1. Put these in `highered-risk` (recommended) or a new `highered-accreditation` server?
2. robots.txt and terms: `ope.ed.gov/robots.txt` could not be read (it redirects to an ed.gov page, and my request was blocked by a web application firewall), and I found no terms page for DAPIP. The file is a public federal dataset fetched through the same endpoint as the site's Download button, once a month per user. Comfortable proceeding on that basis, with the question noted in SECURITY and the README, or do you want to email the Department first?
3. Refresh interval 30 days (recommended) or the 90 days used elsewhere?
4. Include programmatic accreditors (nursing, radiologic technology and so on)? Recommended yes: that is the part the Test College A brief missed.

## Milestone 6 note (2026-10-31): built (`highered-accreditation`)
Owner decisions: new server (not part of `highered-risk`); proceed despite the unreadable robots.txt; 30-day refresh; include programmatic accreditors and state boards.
Built: `get_accreditation_status` and `get_accreditation_actions` (121 tests plus 1 live, mutation-checked, stdio session through `uvx`). Differences from the proposal: the scope enum gained `state` (records from state agencies); the POST body is fixed in code with no caller-controlled parameter; categories are loss, adverse, monitoring, resolved, routine, substantive_change, closure, agency_recognition and unclassified.
State boards: DAPIP carries only seven state agencies (Maryland and Missouri boards of nursing, New York Regents and Office of the Professions, and career-technical boards in Oklahoma, Pennsylvania and Puerto Rico). They are included and listed in every status response. There is no national feed for other states' board actions, so Massachusetts (Test College A) has none; the tools and SKILL say so instead of implying a clean result.
Still open: state board approvals for other states (each state publishes separately), agency-site detail (not crawled), Census PSEO, sub-state projections, BLS policy confirmation, `.mcpb` bundles, PyPI publishing, Windows.
