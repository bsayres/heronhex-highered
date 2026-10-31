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

## Milestone 2 note (2026-10-31): part 1 done, part 2 blocked
Built: `servers/highered-risk` with `get_fsa_status(opeid)` (HCM, composite scores, cohort default rates), 23 tests, live run, uvx session, docs.
New dependencies: `openpyxl` (FSA .xlsx files, read-only mode) and `xlrd` (composite scores exist only as legacy .xls). Dev-only: `xlwt` (builds the .xls test fixture).
Design choice: the tool takes an 8-digit OPEID (resolve it with highered-institutions) instead of a UNITID, so the servers stay independent.
Blocked: `get_audit_findings` needs a free FAC API key to verify the API live. Deferred as planned: accreditor actions, EMMA.
Open: composite scores lag about two years and omit public institutions; confirm that is acceptable for the "Title IV financial responsibility score" question.
