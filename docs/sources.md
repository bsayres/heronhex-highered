# Data sources

Research date: **2026-10-30**. "VERIFIED" means I hit the endpoint or read the primary file today. "UNVERIFIED" means I could not confirm it and **nothing is built on it** until resolved. Rate limits and terms I could not read from a primary page are marked as such.

Test institution used for probes: Harvard University (UNITID 166027).

## Summary

| Source | Access | Auth | Milestone | Status |
|---|---|---|---|---|
| Urban Institute Education Data API (IPEDS) | REST | none | 1 | VERIFIED live; **robots.txt conflict, see below** |
| College Scorecard API | REST (api.data.gov) | free key | 1 | VERIFIED live (DEMO_KEY) |
| Carnegie Classifications | bulk XLSX (ACE) + fields inside Urban IPEDS directory | none | 1 | Fields VERIFIED via Urban; ACE file URL UNVERIFIED |
| ProPublica Nonprofit Explorer | REST | none | 1 | VERIFIED live; **license conflict, see below** |
| FSA Data Center (composite scores, HCM, CDR) | bulk downloads | none | 2 | UNVERIFIED (download URLs not found) |
| Federal Audit Clearinghouse API | REST (PostgREST) | free api.data.gov key | 2 | Docs VERIFIED; live call blocked (no key) |
| NSF NCSES HERD | bulk / Table Builder | none | 3 | Page exists; UNITID field UNVERIFIED |
| NSF Awards API | REST | none | 3 | VERIFIED live |
| NIH RePORTER API v2 | REST (POST) | none | 3 | VERIFIED live |
| Grants.gov search2 | REST (POST) | none observed | 3 | VERIFIED live; what it covers is opportunities, not awards |
| SHEEO SHEF | bulk downloads | none | 3 | Terms VERIFIED (attribution); file URLs UNVERIFIED |
| WICHE Knocking at the College Door | bulk XLSX | none | 3 | Terms partly verified; **state-level only** |

## Issues needing your decision (read first)

1. **Urban `robots.txt` has `Disallow: /api/`** (also `Crawl-delay: 1`). The API is the documented programmatic interface, but your rules say respect robots.txt and report rather than work around. Options: (a) proceed, treating robots.txt as aimed at crawlers and honoring a 1 req/sec delay, after emailing Urban to confirm; (b) use Urban's CSV bulk downloads (the FAQ points to a Downloads tab, URL UNVERIFIED) instead of the API; (c) go to NCES/IPEDS bulk files directly. I have **not** decided this for you.
2. **ProPublica Nonprofit Explorer is licensed CC BY-NC-ND 3.0 US** per its data-store page, with a ban on charging for viewing or selling ads against the data, and "commercial users should contact us". That is not MIT-compatible for redistribution of data, and ND may bar derived tables. A tool that fetches on demand and returns small fields may be acceptable for non-commercial use, but I'm not a lawyer. Options: (a) keep it as an optional, clearly labeled non-commercial source; (b) replace with IRS 990 bulk data (public domain; access method not yet researched); (c) drop EIN-from-990 and use only the EIN carried in IPEDS. Recommend (c) for the crosswalk (IPEDS already carries EIN) and treat ProPublica as optional for financials.
3. **WICHE projections are state-level (and state x race), not institution-level.** `get_enrollment_projection` can only report the institution's state/region high-school-graduate outlook, labeled as such.
4. **HERD UNITID presence is UNVERIFIED**, so the Milestone 3 join rule stands: join via crosswalk and flag fuzzy until the codebook confirms.
5. **Scorecard DEMO_KEY returned `x-ratelimit-limit: 10`**, not the 30/hour a secondary source cites. Use a real free key; do not rely on any number until read from a primary page.

## 1. Urban Institute Education Data API (IPEDS)

- Base: `https://educationdata.urban.org/api/v1/` , pattern `college-university/ipeds/{endpoint}/{year}/[specifiers]/?filters`. VERIFIED.
- Auth: none. Rate limit: not stated on the docs page (UNVERIFIED); robots says `Crawl-delay: 1`. Results are paginated (`count`, `next`); other sources say 10,000 per page (UNVERIFIED).
- License: ODC-By 1.0, cite portal and dataset, "as is" (VERIFIED from docs page).
- `directory/{year}` (VERIFIED for 2022, 2023, 2024 return 200) carries the identifiers we need, all in one record:
  - `unitid` (int), `opeid` (8-char string, e.g. `00215500`), `ein` (9-digit string), `duns` (often blank), **`ueis`** (field exists; population and format UNVERIFIED, test on more institutions), `url_school` (domain source), `inst_name`, `state_abbr`, `inst_system_flag`, `inst_system_name`, `inst_control`, `sector`, `degree_granting`, `currently_active_ipeds`, `date_closed`, `newid`.
  - Carnegie fields: `cc_basic_2010/2015/2018/2021/2025`, `cc_research_act_desig_2025`, `cc_instit_size_2025`, and others. So Carnegie classes can come from the directory with no separate download.
- `fall-enrollment/{year}/{level_of_study}/` with `?unitid=` returns disaggregated rows (`ftpt`, `sex`, `race`, `enrollment_fall`); value 99 = total. 96 rows for one institution-year at the all-students endpoint, so the tool must filter to totals. VERIFIED for 2022-2024.
- Year coverage for `fall-enrollment` back-years: UNVERIFIED beyond the three years probed.
- `inst_system_name` is a free-text label, `-2` when absent; it is not a system identifier. Multi-campus handling needs OPEID (see below).

## 2. College Scorecard API

- Base: `https://api.data.gov/ed/collegescorecard/v1/schools` , `api_key` query param. VERIFIED (DEMO_KEY, 10/hr observed).
- The docs URL I tried (`collegescorecard.ed.gov/data/documentation/`) returns 404; the data dictionary XLSX at `https://collegescorecard.ed.gov/assets/CollegeScorecardDataDictionary.xlsx` was read.
- Identifier fields (VERIFIED live): `id` = UNITID, **root-level** `ope8_id` and `ope6_id` (not under `school.`), `school.main_campus`, `school.name`, `school.state`, `school.school_url`, `school.carnegie_basic/undergrad/size_setting` (older Carnegie scheme), `accreditor` (listed in dictionary under `school`; value not seen for Harvard).
- **No EIN field found** in Scorecard (`school.ein` returned nothing). EIN comes from IPEDS directory.
- Rate limit with a registered key: 1,000/hr/IP per a secondary source. UNVERIFIED against a primary page.
- Terms: public US government data; no restriction text read. Key signup is free at api.data.gov/signup.
- Use in Milestone 1: outcomes/cost context in `get_institution_profile`, and OPEID6 grouping for multi-campus checks.

## 3. Carnegie Classifications

- The Urban directory already includes 2010 to 2025 classification codes, so the minimum viable path needs no Carnegie download. VERIFIED.
- ACE hosts the "2025 Research Activity Designation Public Data File" (XLSX) and the IU site hosts data files. Exact current URL UNVERIFIED. `robots.txt` on carnegieclassifications.acenet.edu sets `Crawl-delay: 600` (crawler guidance); a single on-demand file download is not crawling, but I'll report rather than assume.
- Code-to-label mapping (e.g. basic 15 = "Doctoral Universities: Very High Research Activity" in the 2010 scheme) must come from the Carnegie documentation; the 2025 label set is UNVERIFIED. Until then return codes with a null label and a reason.

## 4. ProPublica Nonprofit Explorer API

- Base: `https://projects.propublica.org/nonprofits/api/v2` , `GET /search.json?q=&page=` and `GET /organizations/{ein}.json`. VERIFIED live (search returned 13 results for "harvard university").
- Auth: none. Rate limit: not stated (only `pdf_url` links are rate limited).
- Fields: `ein` (integer, **leading zeros trimmed**), `strein` ("XX-XXXXXXX"), `ntee_code`, `subseccd`. IPEDS `ein` is a 9-digit string with zeros, so normalize both to 9-digit zero-padded strings.
- Name search returns related entities (e.g. a band, a trustee entity). For Harvard, IPEDS EIN `042103580` is the President and Fellows; the top search hit was a different EIN. **Matching by name is unsafe; fetch by EIN only.**
- License: CC BY-NC-ND 3.0 US per the data-store page, Data Terms of Use at `propublica.org/about/propublica-data-terms-of-use` (text not read). See decision 2.
- 990 filings name officers and key employees. Tools must not return those fields.
- `robots.txt` on the host disallows only specific other paths; `/nonprofits/api` is not disallowed.

## 5. FSA Data Center (Milestone 2)

- Pages: `studentaid.gov/data-center/school/composite-scores`, `.../hcm`, and default-rates pages return HTTP 200 but are **JavaScript shells** (identical 10,888-byte HTML); the actual file links did not appear in the static HTML. **Download URLs, file formats, and update cadence are UNVERIFIED.**
- `robots.txt`: `Crawl-delay: 7`; no disallow on `/data-center/`.
- Secondary sources say: composite scores are published as XLSX with a lag (a 2022 announcement added 500+ scores to a 2019-20 report); the HCM list is posted by FSA; cohort default rates are on fsapartners.ed.gov and the Data Center. None confirmed.
- Join key expected: OPEID (8-digit, branch-level) and school name. Per-branch rows mean one-to-many against UNITID.
- Next step: open the pages in a browser (or inspect the XHR) to find stable file URLs. Milestone 2 does not start until that is resolved.

## 6. Federal Audit Clearinghouse API (Milestone 2)

- Base: `https://api.fac.gov`, header `X-Api-Key`, free key from api.data.gov (signup at fac.gov/api/signup). Unauthenticated call returned `403 API_KEY_MISSING`. VERIFIED.
- Rate limit: 1,000/hr/key by default (from FAC docs via search; page not re-read).
- Tables/fields from the data dictionary (VERIFIED names): `general` (`auditee_uei`, `auditee_ein`, `auditee_name`, `auditee_state`, `audit_year`, `fy_end_date`, `is_internal_control_material_weakness_disclosed`, `is_going_concern_included`, `is_low_risk_auditee`, `is_modified_opinion`, `is_material_noncompliance_disclosed`), `findings` (`finding_ref_number`, `is_material_weakness`, `is_significant_deficiency`, `is_questioned_costs`, `is_repeat_finding`), `findings_text` (free text, untrusted), `federal_awards`. Exact endpoint paths and filter syntax: not live-tested (no key).
- Terms: public per 2 CFR 200.512; Tribal entities may restrict findings text for FY2019+, so absent rows must not be read as "no findings".
- Join keys: UEI and EIN. IPEDS gives EIN and (maybe) UEI, so audits join by identifier when present. Many institutions file under a system or foundation entity, so a null result is not proof of no audit.
- **I need a free FAC key from you (or you register one) to live-verify.** Key stays in env var `FAC_API_KEY`.

### Update 2026-10-31: FAC verified live (Milestone 2)
- `GET https://api.fac.gov/<table>` with header `X-Api-Key` returns a JSON array (PostgREST). Filters are `column=eq.value`, `report_id=in.(a,b)`, `findings_count=gt.0`; `select`, `order`, `limit` work. Rate limit headers show 1000/hr. Hostile filter values (quotes, operators) are treated as data and match nothing.
- `general`: `auditee_ein` (9 digits), `auditee_uei`, `audit_year`, `fy_end_date`, `fac_accepted_date`, `gaap_results`, the `is_*` flags (values "Yes"/"No"), `total_amount_expended`, `resubmission_status` (seen: `most_recent`). It also carries auditee and auditor contact names, emails and phones: **never requested**.
- `findings`: structured only (`reference_number`, `award_reference`, `type_requirement`, `is_*` flags with "Y"/"N"). No narrative. Joins to `federal_awards` on `report_id` + `award_reference` for program name and ALN (`federal_agency_prefix` + `federal_award_extension`).
- Test College A (EIN 999000001, UEI TESTCOLLEG1A): reports for 2022, 2023, 2024; 2024 has 10 findings (9 on Pell, 1 on Federal Work-Study). The 2023 report flags a material weakness with no `findings` rows (upstream inconsistency, surfaced as a warning).
- Not used: `findings_text` (free text), `additional_eins`, `notes_to_sefa`, `corrective_action_plans`.

## 7. NSF NCSES HERD (Milestone 3)

- Survey pages: `https://ncses.nsf.gov/surveys/higher-education-research-development/2024` (200). Public-use microdata from FY1972, latest FY2024; Table Builder from 1973; FY2024 has 55 tables vs 86 in FY2023.
- **UNITID in each year: UNVERIFIED.** Plan: download the FY2024 and one older public-use file and read the codebook. If UNITID is absent in a year, join through name/state and mark `match_basis: fuzzy`.
- File URL, format (CSV or SAS/Stata), and license text: UNVERIFIED. NSF data is generally public domain; confirm.

## 8. NSF Awards API, NIH RePORTER, Grants.gov (Milestone 3)

- NSF: `https://api.nsf.gov/services/v1/awards.json?keyword=&printFields=&rpp=` , no key, VERIFIED. Returns `abstractText` (untrusted free text). `robots.txt` is 404 on that host.
- NIH RePORTER: `POST https://api.reporter.nih.gov/v2/projects/search`, JSON criteria (`org_names`, `fiscal_years`), no key, VERIFIED. Org records carry `org_duns`, **`org_ueis`**, and `primary_uei`, so NIH can join to institutions by UEI when the crosswalk has one; otherwise by exact org name (fuzzy). NIH asks for no more than 1 request/second and off-peak bulk use per its API docs (UNVERIFIED here; confirm).
- Grants.gov `POST https://api.grants.gov/v1/api/search2` returned `Webservice Succeeds` with 456 hits for "higher education", no key. It lists **funding opportunities, not awards to an institution**; `search_grant_awards` may therefore cover NSF and NIH awards only, with Grants.gov offered as an opportunity search or dropped. Decision for you.

## 9. SHEEO SHEF (Milestone 3)

- Terms: data "may be freely used with appropriate attribution and citation" (FY24/FY25 report text, VERIFIED via search). Reports through FY25 exist.
- Granularity: state and sector level in the main downloads; **SHEF Expansion** adds institution-level files for 2008-2022 with a codebook (per search result, UNVERIFIED on production site).
- `robots.txt`: `Crawl-delay: 10` on sheeo.org.
- File URLs and formats: UNVERIFIED.

## 10. WICHE Knocking at the College Door (Milestone 3)

- 11th edition published Dec 2024 (per search). 10th edition required the attribution "Source: Western Interstate Commission for Higher Education, Knocking at the College Door: Projections of High School Graduates, 2020." The 11th's terms and file URLs: UNVERIFIED.
- Granularity: state (and state x race/ethnicity) high school graduate projections. Not institution-level.

## Identifier map

| Identifier | Authoritative field | Notes |
|---|---|---|
| UNITID | Urban `unitid`; Scorecard `id` | 6-digit string/int; use string `^\d{6}$` |
| OPEID | Urban `opeid` (8 chars); Scorecard `ope8_id`, `ope6_id` | One OPEID6 can cover several UNITIDs (branches); FSA is keyed by OPEID |
| EIN | Urban `ein` (9-digit string) | ProPublica returns integer; normalize to 9 digits. Not in Scorecard |
| UEI | Urban `ueis` (UNVERIFIED population); NIH `org_ueis`; FAC `auditee_uei` | Verify on a sample of institutions |
| Domain | Urban `url_school`; Scorecard `school.school_url` | Normalize: lowercase, strip scheme, `www.`, path |
| System/parent | Urban `inst_system_flag`, `inst_system_name` (free text); OPEID6 grouping | No stable system ID found |
| Carnegie | Urban `cc_*_{year}` | Labels need the Carnegie documentation |

## Using alongside 1102tools servers (documentation task, deferred to repo README)

SAM.gov entity search (UEI, registration status), USAspending (federal awards by recipient UEI), and BLS OEWS (regional wages) are available from 1102tools. The UEI from this crosswalk is the bridge to SAM.gov and USAspending. Documented in root README at Milestone 1.

## 1102tools layout observed

Top level: `.github/workflows` (21 files incl. `publish-pypi.yml`), `badges`, `deploy`, `docs`, `scripts`, `servers`, `shared`, `tests`, `glama.json`, `license`, `readme.md`. Nine server folders under `servers/*-mcp`. Inside a server (`bls-oews-mcp`): `src/<pkg>/`, `tests/`, `scripts/`, `pyproject.toml` (hatchling, `mcp>=2.0.0,<3`, httpx, filelock, platformdirs, `[project.scripts]` entry point), `uv.lock`, `server.json`, `smithery.yaml`, `Dockerfile`, `changelog.md`, `testing.md`, `readme.md`, `license`. Publishing: tag-triggered workflow with PyPI OIDC trusted publishing. **I found no `.mcpb` manifest or workflow** in what I could see (UNVERIFIED); I'll build `.mcpb` packaging from the MCPB spec instead.


## Update 2026-10-31: FSA sources verified (Milestone 2)

- **File discovery**: `https://studentaid.gov/data-center/school/{hcm,composite-scores}.json` returns the page content including file links (undocumented endpoint; VERIFIED). Files live at `https://studentaid.gov/sites/default/files/<name>`.
- **HCM**: `Schools-on-hcm-<mon>-<year>.xlsx`, quarterly; newest seen `Schools-on-hcm-jun-2026.xlsx` (as of 2026-06-01, 491 rows). Columns: ID, **OPEID (8-digit string)**, Institution Name, City, State, Country, Institution Type Desc, Monitor Method, Reason On Description. Includes public institutions. VERIFIED.
- **Composite scores**: legacy `.xls`, newest `ay-22-23-composite-scores.xls` (fiscal years 7/1/2022 to 6/30/2023, eZ-Audit data as of Dec 17, 2024). **Private nonprofit and proprietary only.** Columns include **OPEID (8-digit)** and composite score; needs `xlrd`. VERIFIED.
- **Cohort default rates**: `https://fsapartners.ed.gov/knowledge-center/topics/default-management/official-cohort-default-rates-schools` links "Official CDRs for the past three fiscal years" (`.../sites/default/files/2026-09/EligibleSchoolFileFY2023OfficialFinal.xlsx`, FY2023 cohort). Keyed by **6-digit School Code (= OPEID6)**; three cohort years per row; rates in percent. fsapartners.ed.gov robots.txt allows all. VERIFIED. Test College A (OPEID6 099901) is not in it.
- studentaid.gov robots.txt: `Crawl-delay: 7`.
- **FAC**: VERIFIED live 2026-10-31 (see section 6 update below).
- The "UNVERIFIED download URLs" note in section 5 above is superseded by this section.


## Update 2026-10-31: composite-score alternatives and Milestone 3 sources (all checked live)

### Is there a more current or broader source for financial responsibility?
- **FSA composite scores**: the Data Center page still lists `ay-22-23-composite-scores.xls` as the newest file (fiscal years ending 7/1/2022 to 6/30/2023). No newer file exists; FSA is the only publisher. Public institutions are not scored.
- **IPEDS finance** (Urban `college-university/ipeds/finance/{year}/`, one unified table, 153 fields, includes public institutions such as Test College A): newest year is **2023**. NCES raw files agree (`F2223_F1A.zip`/`F2223_F2.zip` posted 2024-12-06; `F2324_*` returns 404). Same period as the composite scores, so no gain in recency, but it covers publics. Fields differ by `form_type` (GASB public vs FASB private): `net_position` for GASB, `equity_*`/`assets_net` for FASB. A composite score cannot be reproduced from it without estimating, which this project does not do.
- **More current risk signals that already exist**: HCM (as of 2026-06-01) and FAC audits (accepted through 2026-05-12, includes `is_going_concern_included`).

### HERD (NSF NCSES): VERIFIED
- Microdata page `https://ncses.nsf.gov/explore-data/microdata/higher-education-research-development` links one zip per year, e.g. `/821/assets/0/files/higher_education_r_and_d_2024.zip` (7.5 MB; holds `herd2024.csv` 49 MB and a `.sas7bdat`). Latest FY2024, posted Sept 2025. robots.txt: only `/cms/` disallowed.
- **`ipeds_unitid` is present** (also `inst_id`, `ncses_inst_id`). FY2024: 681 institutions, 649 with a UNITID, **32 without** (e.g. Oregon State, University of New Hampshire). Identical header FY2015 through FY2024.
- Long format: `questionnaire_no, question, row, column, data, status`. Values are **thousands of dollars** (user guide). Total R&D by source of funds is questionnaire `01.a`-`01.g` (Federal, State and local, Business, Nonprofit, Institution, All other, Total). Test College A has no HERD rows (below the survey threshold), so the answer is a null with a reason.

### NSF Awards API: VERIFIED, with caveats
- `GET https://api.nsf.gov/services/v1/awards.json`, no key. `ueiNumber` is an exact filter (Penn State: 6,526 awards; `dateStart`/`dateEnd` work). `rpp` max 25, max 3,000 results per query.
- **`printFields` is "no longer functional"**: every record comes back in full, including PI and co-PI names and emails and program-officer name, email and phone. The server must project to a safe field list in code and drop all person fields.
- `awardeeName` is a free-text keyword search that also matches abstracts (a Harvard query returned LSU). Never use it for identity. Boolean operators inside parameter values are parsed by the API; strict UEI validation on our side prevents misuse.

### NIH RePORTER v2: VERIFIED, with caveats
- `POST https://api.reporter.nih.gov/v2/projects/search`, no key. Policy: at most 1 request/second, large jobs off-hours. Offset max 14,999.
- **There is no UEI search criterion.** `org_ueis` is silently ignored and an invalid filter fails open: a junk UEI returned all 2,983,713 projects. Valid criteria are `org_names` (wildcard) and `org_names_exact_match`.
- Workable and still identifier-exact: query by name, then keep only rows whose returned `organization.org_ueis` intersect the institution's UEIs. Tested with Penn State FY2025: 181 rows, all UEI NPM2J7MSCF61. The tool must say results are name-queried and UEI-verified, and warn when truncated.
- Intramural NIH rows have no org UEI and are dropped by the UEI check.

### Grants.gov search2: VERIFIED (opportunities only)
- `POST https://api.grants.gov/v1/api/search2`, no key. Filters: `keyword`, `oppStatuses` (`forecasted|posted|closed|archived`), `eligibilities` (`06` public IHE, `20` private IHE, `25` other), `agencies`, `fundingCategories`, `rows`, `sortBy`. Returns number, title, agency, openDate, closeDate, cfdaList. The response also embeds a JWT `token` and large facet lists; neither is returned by the tool.

### SHEEO SHEF: VERIFIED (state level only)
- `https://shef.sheeo.org/data-downloads/` links `SHEEO_SHEF_FY25_Report_Data.xlsx` (FY1980-FY2025, 52 jurisdictions, 45 columns) and `..._Sector_Data.xlsx` (FY2019-FY2025, two-year vs four-year). Published April 2026 under a dated folder (`/wp-content/uploads/2026/04/`), so the link must be discovered from the page, not guessed. robots.txt allows all.
- Required citation: State Higher Education Executive Officers Association. (2026). State Higher Education Finance: FY 2025. Boulder, CO. Data are unadjusted; divide by the adjustment factors for real dollars.
- No institution-level data in these files. Institution-level SHEF Expansion data (2008-2022) were not located and are not planned.

### WICHE Knocking at the College Door: VERIFIED, LICENSE FLAG
- 11th edition, December 2024. Dataset: `https://www.wiche.edu/wp-content/uploads/2024/12/Knocking-at-the-College-Door-11th-Edition-Projections-Dataset-12-11-2024.xlsx` (12 MB, sheet `Data`, 246,468 rows: `Stabbr, StateRegionUS, ClassOf, SchoolYear, SchoolSector, Grade, RaceEthnicity, Students, ActualProjected, ...`). State, region and US level only.
- **License: CC BY-NC-SA 4.0** (attribution, NonCommercial, ShareAlike). Needs an owner decision (see PLAN).


## Update 2026-10-31: Milestone 4 research (labor-market alignment)

### NACE and CCRC
- **NACE**: the First-Destination Survey report is free to the public (national annual report, not institution-level, not an API). The Salary Survey is member-gated and its summer edition is built from First-Destination data. No NACE data tool is planned. Reuse terms for NACE content (e.g. the career-readiness competencies) were not read; do not embed NACE text until they are.
- **CCRC**: publishes research reports and interactive data tools, no downloadable datasets found. The tools appear to rest on federal data already used here. No data tool is planned; cite CCRC research in SKILL guidance where it applies. Contact ccrc@columbia.edu to ask whether data is offered.

### CIP-SOC crosswalk (NCES + BLS): VERIFIED
- `https://nces.ed.gov/ipeds/cipcode/Files/CIP2020_SOC2018_Crosswalk.xlsx` (429 KB). Sheets: `CIP-SOC` (6,097 rows, columns CIP2020Code, CIP2020Title, SOC2018Code, SOC2018Title), `SOC-CIP`, `Unmatched CIP Codes`, `Unmatched SOC Codes`, `Added Matches`, and others. NCES: "not based on actual empirical data".
- 2,143 CIP codes; median 2 SOC codes per CIP, max 180, 10 CIPs map to more than 10 SOCs. Unmatched CIPs appear as SOC `99-9999` "NO MATCH" and must become explicit nulls. Mappings include postsecondary teachers (nursing 51.3801 maps to 25-1072 nursing instructors and 29-1141 registered nurses), so supply/demand views must show the occupation list, not one number.

### BLS Employment Projections: ACCESS ISSUE
- The current table is "Occupational projections, 2025-35, and worker characteristics, 2025": `https://www.bls.gov/emp/ind-occ-matrix/occupation.xlsx` (employment 2025 and 2035, annual openings, typical entry education, work experience, on-the-job training).
- **`www.bls.gov` and `download.bls.gov` return HTTP 403 "Access Denied" to this project's client, including for `robots.txt`**, with a plain research user agent and with one naming the repository. `api.bls.gov` answers normally but did not expose projections under a guessed series id. Secondhand reports (R and Stata package docs, forum posts) say BLS expects a contact email address in the User-Agent; the official wording was not found. **Not worked around: no browser user agent was spoofed, and the owner's email was not sent.** Decision needed (see PLAN).

### O*NET: VERIFIED
- Database 31.0 is CC BY 4.0, downloadable without a key: `https://www.onetcenter.org/dl_files/database/db_31_0_excel.zip` (also per-file CSV/JSON under `/dl_files/database/db_31_0_csv/`). Includes skills, task statements, software/technology skills. Attribution must name the O*NET 31.0 Database, USDOL/ETA, link the license, and note changes. It does **not** include BLS projections.
- Web Services (v2): free account at `https://services.onetcenter.org/developer/signup`, keys created under My Account, sent in the `X-API-Key` header (never in the query string), GET only, JSON, JSON 429 means wait at least 200 ms. Terms: free if a prominent attribution link to O*NET Web Services is shown; access may be throttled above 5 requests/second or 50,000/day; data may not be altered; use limited to applications the registrant controls. The API serves the latest version; the bulk files do not need it.

### IPEDS completions via Urban: VERIFIED endpoints
- `.../college-university/ipeds/completions-cip-2/{year}/` and `.../completions-cip-6/{year}/` (there is no 4-digit endpoint). Rows are per institution, award_level, majornum, race, sex: use `race=99&sex=99&majornum=1` for totals (Test College A 2023: 28 rows). `cipcode_6digit` is stored as an integer without the dot and leading zero (e.g. 510000, 520201). Code 99 appears as a total. **Award-level codes and the CIP integer encoding must be confirmed against Urban's documentation before building.**

### College Scorecard field of study: VERIFIED via the existing key
- `latest.programs.cip_4_digit` on the schools endpoint returns, per institution, a list of programs (4-digit CIP, credential level, IPEDS award counts, debt, repayment, earnings at 1 year and 3 years). Test College A: 28 programs, 27 with some earnings value, but the institution's own medians are often null (small cell suppression) while `*_national` comparison values are present. The tool must label national comparison values as national and explain suppression as a null with a reason.

### Census PSEO: NEEDS A KEY (deferred)
- API variables confirmed (`INSTITUTION`, `INST_STATE`, `CIPCODE`, `CIP_LEVEL`, `DEGREE_LEVEL`, `GRAD_COHORT`, earnings P25/P50/P75 at 1, 5 and 10 years). The API redirects to a "missing key" page without a free Census API key. Raw state files exist under `https://lehd.ces.census.gov/data/pseo/latest_release/` but their file names were not verified. Coverage is partner institutions only (about 29% of graduates as of the January 2024 release).

### Not verified
- State and regional projections (Projections Central or individual state labor agencies), CareerOneStop API (registration and terms), Credential Engine, O*NET API job-outlook endpoint contents.


### Update 2026-10-31 (build): Milestone 4 access findings
- **BLS access resolved**: with a contact email in the User-Agent, `www.bls.gov/robots.txt` (200; `User-agent: *` disallows only `/scripts`, `/crs`, `/_private`, `/iisadmin`, `/srchadm`, `/advisory/members/`, `/idcf`, `/*print*`), the projections workbook (413 KB) and `download.bls.gov/pub/time.series/ep/` return 200. Without one: 403. The workbook (Table 1.2) is "Occupational projections, 2025-35, and worker characteristics, 2025"; employment and openings are in thousands; typical entry education values: High school diploma or equivalent, Bachelor's degree, No formal educational credential, Doctoral or professional degree, Postsecondary nondegree award, Associate's degree, Master's degree, Some college, no degree. Some occupations appear only as broad groups (last digit 0).
- **Scorecard documentation (October 2026)**: credential levels 1 Undergraduate Certificates or Diplomas, 2 Associate's, 3 Bachelor's, 4 Post-Baccalaureate Certificates, 5 Master's, 6 Doctoral, 7 First Professional, 8 Graduate/Professional Certificates; IPEDSCOUNT1 and IPEDSCOUNT2 are awards for two consecutive award years (counts include second majors); suppressed values are "PS". The schools endpoint accepts leaf subfields such as `latest.programs.cip_4_digit.earnings.1_yr.overall_median_earnings`; asking for a parent object drops its children.
- **O*NET bulk CSVs** (no key): `https://www.onetcenter.org/dl_files/database/db_31_0_csv/{occupation_data,essential_skills,transferable_skills,software_skills,task_statements}.csv` (0.3 to 6 MB each). Version is read from `https://www.onetcenter.org/database.html`. O*NET 31.0 replaced the old Skills file with Essential Skills and Transferable Skills. O*NET-SOC codes (e.g. 29-1141.00) map to SOC by their first seven characters.
- **Urban completions**: award-level codes not decodable without a codebook (see testing.md); not used.


### Update 2026-10-31 (review fixes): sources checked
- **2 CFR 200.512(a)** (eCFR, read 2026-10-31): the reporting package "must be submitted within 30 calendar days after the auditee receives the auditor's report(s) or nine months after the end of the audit period (whichever is earlier)"; if the due date falls on a weekend or federal holiday it is due the next business day; the cognizant or oversight agency "may authorize an extension when the nine-month timeframe would place an undue burden on the auditee." FAC data shows neither extensions nor the date the auditor's report was received.
- **FAC API Data Dictionary** (`https://fac.gov/api/dictionary`, Excel at `/assets/api/FAC%20API%20Data%20Dictionary.xlsx`): `type_requirement` is one or more of A Activities allowed or unallowed, B Allowable costs/cost principles, C Cash management, E Eligibility, F Equipment and real property management, G Matching/level of effort/earmarking, H Period of performance, I Procurement and suspension and debarment, J Program income, L Reporting, M Subrecipient monitoring, N Special tests and provisions, P Other (D and K reserved, no O), alphabetical, no repeats. `is_modified_opinion`: "Indicates if the finding resulted in a modified audit opinion"; "Y" if the auditor identified the finding as the basis for a modified opinion. The `general` table also has `submitted_date`, `auditor_certified_date`, `auditee_certified_date`, `date_created`, `ready_for_certification_date`.
- **Urban IPEDS finance**: for Test College A, `rev_operating + rev_nonoperating + rev_additions` equals `rev_total_current` in FY2020 and FY2023 only; in FY2019, FY2021 and FY2022 it does not (FY2022 has no additions line although `rev_capital_approps` was 4.1M). Capital appropriations therefore cannot be reliably netted out of total revenue.
- **Projections Central (State Projections Consortium)**: the site `https://projectionscentral.org` is a JavaScript app, but it documents a public REST API at `https://public.projectionscentral.org` ("read only https GET requests"): `/Projections/LongTermRestJson/{state FIPS or 'all'}/{SOC code}` (several values joined with `+`), also `LongTermRestXml`, `ShortTermRestJson`, `ShortTermRestXml`; 100 rows per page with a `pager` block. No key. Row fields: `Area`, `Title`, `OccCode`, `Base`, `Projected`, `Change`, `PercentChange`, `AvgAnnualOpenings`, `BaseYear`, `ProjYear`, `STFIPS`, `StateURL` (the state agency's own page). Tested 2026-10-31: Massachusetts registered nurses (29-1141) base 91,850 (2024), projected 94,850 (2034), 4,930 average annual openings; `all` returns 55 areas (50 states, DC, Puerto Rico, Guam, Virgin Islands, and a ' United States' row) all on the same 2024 to 2034 vintage. Sub-state (regional) projections are not in this API. No robots.txt (404) and no terms page was read yet.
