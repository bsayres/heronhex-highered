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
