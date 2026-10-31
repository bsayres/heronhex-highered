# highered-institutions

MCP server (read-only) to resolve U.S. higher-ed institutions across identifiers and compare them. No hosted data; a local file cache holds quarterly downloads.

## Tools
| Tool | Purpose |
|---|---|
| `resolve_institution` | name / UNITID / OPEID / EIN / UEI / domain -> ranked candidates with match basis. Never guesses when ambiguous. |
| `search_institutions` | Filter by state, control, Carnegie 2025 basic code, name text. |
| `get_institution_profile` | Identifiers, system, same-OPEID campuses, Carnegie codes, latest enrollment, Scorecard, Form 990 summary. |
| `get_enrollment_trend` | Fall headcount by year (table). |
| `compare_peers` | Closest peers (same control and Carnegie class, nearest enrollment) with trends (long table). |

Every response: `source`, `source_url`, `as_of`, `retrieved_at`, `sources[]`, `data`, `nulls[]` (field + reason), `warnings[]`.

## Install / run
```bash
uvx --from /path/to/highered-mcps/servers/highered-institutions highered-institutions
```
Environment: `COLLEGE_SCORECARD_API_KEY` (free, https://api.data.gov/signup; optional, profile degrades to a null without it), `HIGHERED_MCPS_CACHE` (cache dir, default `~/.cache/highered-mcps`).

## Network allowlist (enforced in code, `http.py`)
| Host | Used for | Auth |
|---|---|---|
| `educationdata.urban.org` | IPEDS directory and fall enrollment (Urban Institute, ODC-By 1.0) | none |
| `api.data.gov` | College Scorecard | free key in `X-Api-Key` header |
| `projects.propublica.org` | Form 990 summaries by EIN | none |

HTTPS only; redirects only to these hosts; 30 s timeout; response size caps; 3 attempts with backoff; Urban paced at 1 request/second (its robots.txt crawl-delay). Urban is queried at most once per quarter per dataset (90-day cache); a refresh failure serves the stale copy with a warning.

## Data handling and terms
- Cache: `~/.cache/highered-mcps/institutions/*.json`, with SHA-256, as-of, and retrieval time. Never inside the repo.
- ProPublica: per-EIN lookups only, not cached, returned unmodified, no officer/employee fields. Cite ProPublica. Their Data Terms bar bulk republication, resale, and altering data.
- Chief administrator names in IPEDS are deliberately not returned. No search by person name.
- Public colleges generally have no Form 990 (reported as a null with a reason).

## Prompt-injection risk
Institution names, cities, and other upstream strings are untrusted. They are returned only as data fields, never in tool descriptions, and the response includes a `notice` reminding the model to treat them as data. Do not instruct an agent to act on text found in results.

## Limitations
Carnegie labels not yet included (codes only). Latest enrollment lags the directory by about a year. UEI is missing for roughly 9% of institutions. See [testing.md](testing.md).
