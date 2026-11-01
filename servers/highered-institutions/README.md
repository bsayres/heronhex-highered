# highered-institutions

MCP server (read-only) to resolve U.S. higher-ed institutions across identifiers and compare them. No hosted data; a local file cache holds quarterly downloads.

## Tools
| Tool | Purpose |
|---|---|
| `resolve_institution` | name / UNITID / OPEID / EIN / UEI / domain -> ranked candidates with match basis. Never guesses when ambiguous. |
| `search_institutions` | Filter by state, control, Carnegie 2025 basic code, name text. |
| `get_financial_snapshot(unitid, years=1)` | Headline revenues, expenses, assets, liabilities, net position/assets, endowment and more from the latest IPEDS finance survey, in dollars, as reported. Works for public institutions. Never scored or estimated. `years` up to 10 adds a year-by-year history (use it: one year is not a trend); revenue components are returned as reported and capital appropriations are not netted out. |
| `get_institution_profile` | Identifiers, system, same-OPEID campuses, Carnegie codes, latest enrollment, Scorecard. |
| `get_enrollment_trend` | Fall headcount by year (table). |
| `compare_institutions(unitids)` | 2 to 5 named institutions side by side: control, enrollment years, latest finance year, Scorecard cost and outcomes. No ranking or matching. |
| `compare_peers` | Closest peers (same control and Carnegie class, nearest enrollment) with trends (long table). |

Every response: `source`, `source_url`, `as_of`, `retrieved_at`, `sources[]`, `data`, `nulls[]` (field + reason), `warnings[]`.

## Prompt
`institution_brief(institution, format)` is an MCP prompt (shown as a prompt or slash command in clients that list prompts). It asks Claude to build a sourced written brief, one-pager or interactive dashboard for one institution by calling the highered tools in a fixed order, with the same rules as the `institution-brief` skill (no verdicts, nulls reported as gaps, sources and citations kept). It needs the other highered servers to be connected for the sections they provide, and says which sections are missing when they are not. The `institution` argument takes a name or id only (letters, digits and basic punctuation).

## Install / run
```bash
uvx --from /path/to/highered-mcps/servers/highered-institutions highered-institutions
```
Environment: `COLLEGE_SCORECARD_API_KEY` (free, https://api.data.gov/signup; optional: without it the Scorecard call uses api.data.gov's shared `DEMO_KEY`, which allows only about 10 requests, and every response says so), `HIGHERED_MCPS_CACHE` (cache dir, default `~/.cache/highered-mcps`).

## Network allowlist (enforced in code, `http.py`)
| Host | Used for | Auth |
|---|---|---|
| `educationdata.urban.org` | IPEDS directory and fall enrollment (Urban Institute, ODC-By 1.0) | none |
| `api.data.gov` | College Scorecard | free key in `X-Api-Key` header |

HTTPS only; redirects only to these hosts; 30 s timeout; response size caps; 3 attempts with backoff; Urban paced at 1 request/second (its robots.txt crawl-delay). Urban is queried at most once per quarter per dataset (90-day cache); a refresh failure serves the stale copy with a warning.

## Data handling and terms
- Cache: `~/.cache/highered-mcps/institutions/*.json`, with SHA-256, as-of, and retrieval time. Never inside the repo.
- Chief administrator names in IPEDS are deliberately not returned. No search by person name.

## Prompt-injection risk
Institution names, cities, and other upstream strings are untrusted. They are returned only as data fields, never in tool descriptions, and the response includes a `notice` reminding the model to treat them as data. Do not instruct an agent to act on text found in results.

## Limitations
Carnegie labels not yet included (codes only). Latest enrollment lags the directory by about a year. UEI is missing for roughly 9% of institutions. See [testing.md](testing.md).
