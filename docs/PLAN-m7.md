# Plan for the next phase (draft for review, 2026-11-01)

Status: research done, nothing built. Items marked **OPEN** need a decision or a hands-on probe of the source before any code.

## 1. Publishing to the Claude directory

Findings from Anthropic's published docs (claude.com/docs/connectors/building/submission, plugins/submit, plugins/pre-submission-checklist, plugins/build, connectors/building/review-criteria):

- The directory accepts **remote MCP servers** (HTTPS URL) and **plugins**. Local servers packaged as MCPB are no longer accepted; a local server reaches the directory only inside a plugin.
- A plugin's local MCP server loads in **Claude Code and Cowork sessions on the user's computer. claude.ai chat ignores it.**
- Connector review requires the server to call "your own first-party APIs, or APIs you legitimately proxy." Our servers call public third-party APIs.
- A plugin is submitted from a **public GitHub repo** (private allowed during review), by someone on a paid Claude plan.

| | Plugin (local servers + skills) | Remote connector (we host) |
|---|---|---|
| Reach | Claude Code, Cowork (local) | all Claude apps incl. chat |
| Hosting/ops | none | we run a public HTTPS service |
| API keys | each user's own free key via `userConfig` (sensitive) | one shared key: quota and abuse risk |
| Fit with "no hosted data" | yes | no: becomes a service we operate |
| Review risk | pinned `uvx` package is always held for a human reviewer (expected, not a rejection) | API-ownership rule, OAuth/none auth, uptime duty |

**Recommendation:** ship as a plugin first. Revisit a hosted remote variant only if reach beyond Code/Cowork matters enough to take on operating a service.

Work needed for the plugin route:
1. **Add a `title` to all 21 tools.** Today they carry only `readOnlyHint`; the directory requires both.
2. **Publish the servers to PyPI** (needs your explicit go-ahead; trusted publishing already prepared). The plugin must pin exact versions (`uvx highered-risk==1.0.0`); unpinned or local paths are blocked.
3. Plugin folder: `.claude-plugin/plugin.json` (distinctive name, version, author, license), `.mcp.json` with the six servers, `skills/` (reuse each SKILL.md), README of 40+ words that discloses every host contacted, LICENSE.
4. Keys through `userConfig` entries with `sensitive: true`, referenced as `${user_config.KEY}`; never in files.
5. Make the repo public; privacy policy URL (plain statement: no data collected, local cache only, hosts contacted).
6. Name check: "highered-*" is generic and could be held as a look-alike; pick a distinctive plugin name.
7. Run `claude plugin validate`, then the portal's Validate, then submit.
8. **OPEN:** who submits (paid plan, org owner) and the public name/brand.

## 2. Backup and new sources

All of these need a probe of the live file/endpoint, a robots.txt/terms read, and your yes before any code.

| Source | What it adds | Known | OPEN |
|---|---|---|---|
| NCES IPEDS complete data files (`nces.ed.gov/ipeds/use-the-data`) | backup for Urban/Scorecard; direct IPEDS (finance, completions, graduation, HD) | official zipped CSVs, no official API. nces.ed.gov/robots.txt exists and disallows `/collegenavigator/`, `/ccd/` search pages, `/globallocator/`; data-file paths not listed | exact file URLs (the data-center page redirected in a fetch), update cadence, terms |
| IPEDS dual enrollment (first reported 2022-23: students 17 or younger, credit only) | dual enrollment by institution, race, gender | same files as above; first-year data provisional and likely undercounted | which survey file, field names |
| Clery / Campus Safety and Security (`ope.ed.gov/campussafety`) | on-campus crime counts by institution | official Dept. of Education download tool; page is script-rendered; robots.txt returned 403 | actual download URL, format, years, terms. Same host as DAPIP, but your earlier robots.txt approval was for DAPIP only, so I need a new yes |
| College Scorecard field-of-study data | program-level earnings, debt, completers by CIP and credential | already partly used (programs tool) | confirm file/API fields; docs URL I tried returned 404 |
| Financial Value Transparency / gainful employment | program-level debt-to-earnings | not yet researched | locate and confirm public file |

Proposed order: IPEDS files first (backup plus dual enrollment), then Clery, then program outcomes. Each is a Milestone with its own tests, threat-model entry and validation.

## 3. Composed view

A single read-only tool (working name `build_institution_brief`) in a thin new package that calls the existing servers' functions and returns one envelope: identity, peers, finance, Title IV risk, accreditation, funding context, labor-market alignment, with each section's own source, as-of and nulls preserved and no new numbers computed. **OPEN:** new package that depends on the five, or documented skill/prompt only. Recommendation: skill first (no new attack surface), tool only if the skill proves unreliable.

## 4. Leader-question test (item 2)

Write 15-20 short, plain questions the way people actually ask (for example "Is Test College A in trouble with the feds?", "Who are our real peers?", "Can we afford to add nursing?"), run each through Claude with the servers attached, and score: answered / partly / not, source cited, any wrong or misleading statement. Output: `docs/question-test-<date>.md`. Needs Claude Desktop restarted with the servers loaded; I can run the tool calls myself but cannot drive Claude Desktop's chat, so **OPEN:** you run the questions in Desktop and paste the answers back, or I simulate by calling the tools for each question and judge coverage only (weaker).

## 5. Industry audit

Sources found so far: 2026 EDUCAUSE Top 10 "Making Connections" (eight of ten items confirmed: #1 Collaborative Cybersecurity, #2 Human Edge of AI, #3 Data Analytics for Operational and Financial Insights, #5 Knowledge Management for Safer AI, #6 Measured Approaches to New Technologies, #7 Technology Literacy for the Future Workforce, #9 AI-Enabled Efficiencies and Growth, #10 Decision-Maker Data Skills and Literacy; #4 and #8 not retrieved, the EDUCAUSE page returned 403). ATD: Institutional Capacity Framework includes a Data and Technology domain; a specific 2026 priorities document was not found. Still to cover: AGB, NACUBO, AIR, Inside Higher Ed/Chronicle surveys, Lumina, Strada/Gallup, state-system dashboards.

Caveat: the EDUCAUSE list is about IT issues, so only items 3, 6 and 10 bear on public-data tools. Most of the list (cybersecurity, AI governance) is outside what this toolset can address, and the audit will say so.

## 6. Verifying the unverified items

- SHEEO two- and four-year columns: recompute from the SHEEO sector file independently.
- O*NET tasks, software and transferable-skill sections: compare against the O*NET database files.
- IPEDS itself: becomes checkable once the direct IPEDS source exists (compare Urban/Scorecard values to the NCES files).
- Accreditor directories: still deferred by you.

## Probe results (2026-11-01, read-only GETs and HEADs, no bulk crawling)

- **nces.ed.gov/robots.txt** is readable and does not disallow `/ipeds/datacenter/data/`. IPEDS complete files are direct CSV zips: `https://nces.ed.gov/ipeds/datacenter/data/<NAME>.zip` (HD2024, EF2023A/B/C/D, EF2023A_DIST, EFFY2024, IC2023, DRV* all return 200; 2024 fall files such as EF2024A are not out yet, EFFY2024 is). Dictionaries sit beside them as `<NAME>_Dict.zip` (xlsx). The Data Center pages redirect to a login-style URL, so we use the file URLs only. File names change by year, so the server must discover the latest rather than hard-code it.
- **Retention is in IPEDS.** EF2023D carries full-time and part-time retention fields (for example RET_PCF); Test College A's row is present. This is a cheaper way to answer "what is our retention" than anything we have now.
- **Dual enrollment.** IC2023 has yes/no flags that an institution enrolls high school students for credit (ENRHSST, ENRHSST1 within a dual enrollment program, ENRHSST2 outside one). EF2023B has an "age under 18" category. I did **not** find the dual-enrollment *student counts* NACEP describes in the EF2023 A-D, EFFY2024 or A_DIST dictionaries; they may sit in a file I have not located. Open until found.
- **ope.ed.gov/campussafety** publishes no robots.txt (404 under the app; `ope.ed.gov/robots.txt` redirects to ed.gov). Its own JavaScript shows a public API at `/campussafety/api/`; `dataFiles/years`, `fileTypes` and `fileList` return JSON, and files download by GET at `dataFiles/file?fileName=...`. Latest is `Crime2025EXCEL.zip` (calendar years 2022-24).
  - **Cost:** the zip is 38 MB and holds about 120 MB of **legacy .xls and .xlsx** files plus .doc codebooks, one pair per crime/arrest/discipline/VAWA/hate category and location type (29 files). Reading them needs an Excel parser (xlrd/openpyxl), a new dependency that opens untrusted binary files, and a much larger cache than anything we hold today. SPSS and SAS versions are also binary. No CSV option.
  - Recommendation: do not build Clery until you decide the dependency and size trade-off is worth it. A middle path is to read only the summary files (`Reportedcrime*`, `Reportedvawa*`) from the zip, in memory, with strict size caps.
- **Clery: skipped by decision (2026-11-01).** Not built.
- **Financial Value Transparency (probed 2026-11-01):** no usable public file today.
  - `studentaid.gov/data-center/school/ge` is reachable (not blocked by robots.txt; Crawl-delay 7 already honored by the risk server) but only offers the **2015** gainful-employment debt-to-earnings spreadsheets (`GE-DMYR-2015-Final-Rates.xls`, `GE_SSA_Earnings_2014.xls`), which are old and legacy .xls.
  - The 2023 FVT/GE rule's program information website was planned but I found no published program-level file. One secondary source says the framework was renamed "Student Tuition and Transparency System (STATS) and Earnings Accountability" with a July 1, 2026 date, and the Federal Register lists an April 2026 earnings-premium proposal; I could not confirm either from a primary source (the NASFAA page returned 403). Status is in flux.
  - **Recommendation: do not build.** College Scorecard field-of-study data already supplies program-level debt and earnings (used by `get_program_outcomes`), and the Scorecard "Most Recent Data by Field of Study" file is 34 MB, updated 2026-10-15. Revisit when the Department publishes a program-level file with a stable URL.

## Decisions I need

1. Plugin first, hosted connector later (or never)? 
2. PyPI publishing: go-ahead, and the account and name to use.
3. OK to probe nces.ed.gov and ope.ed.gov/campussafety files, including the robots.txt that returned 403?
4. Brief as skill first, or build the tool now?
5. Question test: you drive Claude Desktop, or I run the tool calls?
