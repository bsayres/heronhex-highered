# Threat model (half page)

**Assets:** the user's machine (files, shell), their API keys, the integrity of answers.
**Trust boundary:** the model and user are trusted; every upstream byte (JSON, names, text) is not.

| Threat | Mitigation |
|---|---|
| Prompt injection via upstream text (names, program names, later: grant abstracts; audit narratives are deliberately not fetched) | Text returned only as labeled data fields; static tool descriptions; `notice` field; skills tell the model to treat it as data; no tool takes instructions from data. |
| Malicious or malformed tool input | pydantic types, length caps, strict regex for identifiers, enums for filters; reject, never sanitize; validation runs before any network call. |
| SSRF / data exfiltration through outbound calls | URLs are fixed per source; HTTPS only; host allowlist checked before each request and each redirect hop; no user-supplied URLs; credentials-in-URL rejected. |
| Key leakage | Keys read from env only, sent in headers, never in URLs, logs, errors, fixtures, or the repo; `.env` ignored; gitleaks in CI. |
| Local file abuse | Read-only server; writes only to the cache dir via a name regex plus resolved-path and symlink check; atomic replace; no archives extracted in M1; downloaded data is parsed as JSON only, never executed. |
| Resource exhaustion | Response size caps, timeouts, bounded retries, page cap, per-host pacing. |
| Poisoned or tampered cache | SHA-256 checked on read; mismatch treated as a miss. |
| Supply chain | Lockfile, pip-audit and Dependabot, Actions pinned to commit SHAs, least-privilege workflow permissions, PyPI trusted publishing (OIDC). |
| Personal data | Only needed fields returned; officer/employee and chief-administrator fields dropped; no person-name search. |

**Residual risks:** a compromised upstream can serve false numbers (answers cite sources and dates so users can check); a compromised dependency; the model may still be influenced by text it reads despite labeling.

## Additions for highered-funding (Milestone 3)
| Risk | Control |
|---|---|
| Upstream returns personal data we did not ask for (NSF returns PI, co-PI and program-officer names, emails, phones for every award and ignores field selection) | Fixed projection to award fields in code; person fields dropped before anything is returned; tested with person data in the mock |
| POST-capable client widens the attack surface | POST only to `api.reporter.nih.gov` and `api.grants.gov`, checked before the request; redirects never followed on POST; bodies built from validated inputs only |
| Upstream filter fails open (NIH returns everything for an unknown criterion) | The server never trusts a server-side filter for identity: every NIH row's own `org_ueis` is checked against the institution's UEIs; truncation and "nothing verified" are reported |
| Hostile or oversized archive (HERD zip) | 25 MB download cap, only the expected CSV member read, decompressed bytes counted while streaming with a hard cap, nothing extracted to disk |
| Unicode digits pass `\d` validation | All validation patterns use `[0-9]`; full-width-digit negative tests in every server |
| Boolean operators in NSF parameter values are interpreted by the API | UEI inputs validated to `[A-Z0-9]{12}` before use; injection-shaped inputs rejected |
| License obligations for redistributed data (WICHE CC BY-NC-SA 4.0) | Nothing hosted or bundled; license and citation returned in every WICHE response; documented in the README and SKILL |

## Additions for highered-labor-market (Milestone 4)
| Risk | Control |
|---|---|
| A user-supplied contact email is sent to a third party (BLS requires one in the User-Agent) | Sent only to `www.bls.gov`, attached per request hop so a redirect cannot carry it elsewhere; never in URLs, bodies, output, descriptions, logs or errors; strict address pattern with `\Z` (no trailing newline, no CR/LF) checked before any BLS request; absent address gives a clear instruction, not a guess; tested across all hosts |
| `$` in Python patterns matches before a trailing newline | All internal `re` patterns use `\Z`; Pydantic patterns reject newlines already |
| Misleading analytics (a single "alignment" number from a loose, non-empirical crosswalk and national data) | The alignment tool returns tables and two disclosed totals, never a score or ratio; every response carries caveats; the SKILL forbids presenting national openings as local demand |
| Bulk O*NET and workbook downloads | Strict URL construction from a discovered version, size caps per file, workbook zip-bomb check, parse failures reported safely, nothing written outside the cache |
| License obligations (O*NET CC BY 4.0) | Credit, version and license link returned with every O*NET response |

## Additions for state projections (Milestone 5)
| Risk | Control |
|---|---|
| A new host with a different request style (path-based filters joined with '+') | Host allowlisted, GET only; state is a fixed enum mapped to FIPS in code and SOC codes are validated `[0-9]{2}-[0-9]{4}`, so a caller cannot inject path segments, `+` lists or 'all'; at most 100 codes per request |
| Upstream returns rows for other areas or occupations | Every row is validated and kept only if its area and occupation were requested; dropped rows are counted and reported; nothing relies on the API's own filtering (tested by mutation) |
| Upstream links (agency URLs) are untrusted | Only https URLs without whitespace and under 300 characters are passed through, as data; the server never fetches them |
| The BLS contact address leaking to a second host | The address is attached only to `www.bls.gov` per hop; a test checks it is absent from every Projections Central request |
| Misleading comparison of state and national numbers from different years | Each row carries its own years; the same-source United States row is returned for comparison; warnings and the SKILL forbid mixing with BLS 2025-35 |
