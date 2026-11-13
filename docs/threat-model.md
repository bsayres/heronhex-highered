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

## Additions for FAC finding text (highered-risk) and highered-funding (Milestone 3)
| Risk | Control |
|---|---|
| FAC finding narratives and corrective-action text are free text and can name staff; the structured audit tool never fetches them | `get_finding_text` is a separate opt-in tool: exact report id only (strict pattern), no name or text search, three fields requested, each text capped at 6,000 characters and stripped of control and invisible formatting characters, returned as labeled data with the untrusted-text notice, and every response warns that names may appear; tested with an injection string and control characters in the mock |
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
| A page link or archive member steers the OEWS download elsewhere | The wage file URL is rebuilt from a two-digit year found in a link on `www.bls.gov` only (links to other hosts are ignored); the archive is read in memory, only the exact workbook member name is read, entry count and total uncompressed size are capped, the download is size-capped, and the workbook is opened read-only; each is mutation-tested |
| The BLS contact address leaking to a second host | The address is attached only to `www.bls.gov` per hop; a test checks it is absent from every Projections Central request |
| Misleading comparison of state and national numbers from different years | Each row carries its own years; the same-source United States row is returned for comparison; warnings and the SKILL forbid mixing with BLS 2025-35 |

## Additions for highered-accreditation (Milestone 6)
| Risk | Control |
|---|---|
| A POST to a federal host (the first server whose only request is a POST) | POST allowed to one exact URL on `ope.ed.gov` with a fixed body that no caller can change; a different URL, scheme, port, credentials or look-alike host is blocked before any request; redirects on the POST are refused, not followed |
| Hostile or oversized zip | Members must be exactly the three expected names (no extras, no duplicates, no nested or traversal names); encrypted zips refused; declared size, total size and compression ratio checked before reading; each member read with a bounded read; zip held in memory, nothing extracted to disk or executed; a parse failure is never cached |
| Personal data in the source (administrator names, emails, phone numbers, street addresses) | Dropped at parse time, so they are never cached or returned; a test plants sentinel values and searches every response and the cache file |
| Misleading status ("Accredited" stays on ended records) | `current` is computed from the end date and explained in `status_note`; the response warns when it overrides the recorded status; tested by mutation |
| Tool-made categories read as the agency's verdict | `category` is documented as this tool's grouping beside the agency's verbatim wording; unknown wording is `unclassified`; no score, rank or label; the SKILL forbids "in trouble" style conclusions |
| Free text from agencies (justification detail, names) | Control characters removed, length capped, returned as labeled data under a notice, never in tool descriptions |
| Absence read as proof (unmatched UNITID, a state with no board in DAPIP) | Explicit nulls with reasons; the state agencies DAPIP carries are listed in every status response |
| robots.txt and terms could not be read for `ope.ed.gov` | Recorded in the README, testing.md and SOURCES; one download per 30 days per user, through the endpoint the site's own Download button uses; owner approved on that basis |

## Additions for IPEDS retention files (highered-institutions, later addition)
| Risk | Control |
|---|---|
| A new host (`nces.ed.gov`) widens what the institutions server can reach | Added to the allowlist, README and this table together; HTTPS only, redirects checked per hop against the allowlist, 1 request per second pacing; NCES's robots.txt allows `/ipeds/datacenter/data/`; tested with a redirect to another host, a different host and plain http |
| A zip that expands enormously, holds many files, or names a file to escape the folder | Read in memory only; zip size cap 3 MB, entry cap 10, uncompressed total cap 20 MB, member cap 8 MB; only a member whose whole name matches `ef{year}d.csv` or `ef{year}d_rv.csv` for the requested year is read, so `../`, subfolders, other years and wrong case are refused; nothing is extracted to disk; each limit is mutation-tested |
| A malformed or changed CSV layout silently yields wrong numbers | Columns are found by header name and required columns must all be present, otherwise the file is refused; rows with a UNITID that is not exactly six digits are dropped; unknown flag codes are reported as not in IPEDS's dictionary instead of being interpreted |
| A provisional file is used instead of the revised one | The `_rv` file is preferred when both are present (tested with different values in each) |
| Cache names built from a year | The year is an integer between 1990 and 2100 and the name pattern allows only lowercase letters, digits, dot, dash and underscore |

## Additions for the hosted connector (`servers/highered-hosted`)
The same five servers run as one process on a server we operate, so the trust boundary moves: the operator can now see what users ask, many users share one process, one cache and one set of keys, and the endpoint is reachable from the internet.

| Risk | Control |
|---|---|
| The operator sees users' tool calls (institution ids and names, states, codes) | No access log (uvicorn's is off), no request logging anywhere in project code (loggers only ever name an upstream host), stateless transport (no sessions, no cookies), nothing user-derived written except public-data cache files named by public identifier; the privacy policy says exactly this |
| Shared keys and contact address | They are the operator's, required at startup (no silent demo-key fallback for a public URL), read from the environment and sent only to `api.data.gov`, `api.fac.gov` and `www.bls.gov` as before; the api.data.gov hourly limit is shared by all users, which caps Scorecard- and FAC-backed calls (acceptable at the expected load; a per-client limit is the next control if needed) |
| One user's slow or heavy call stalls everyone (one event loop) | Bulk parsing runs in worker threads; cache reads are memoized per file so warm calls do not re-parse multi-megabyte JSON; pacing locks are per host; bulk files are pre-warmed at image build so no user request triggers a first download; the 45-second deadline still returns partial results |
| Shared cache written by concurrent calls | Writes are atomic (`os.replace`) with a per-write temp name; the SHA-256 check turns any interleaving into a miss, never corrupt data; the cache holds public data only, so no user can read another's data from it |
| Requests from hosts or origins we do not serve (DNS rebinding, embedding) | The SDK's Host and Origin checks are on, allowing only the configured public host names; non-JSON POST bodies and bodies over 4 MiB are refused before any handler runs |
| The process itself | Runs as a non-root user in a minimal image; writes only to the cache directory; no shell, eval, or dynamic import anywhere (unchanged); health endpoint returns a fixed status and version only |
| Request headers resent on a redirect | API-key headers follow a redirect only to another host on the same server's allowlist (the hop is checked first); the three key-carrying hosts have never redirected, and a redirect elsewhere is refused before the request is made |
| Abuse of a free public endpoint (floods) | The host's connection limits and the servers' own upstream pacing and size caps; no per-client quota yet (documented gap); the server can be restarted or scaled to zero at any time without losing anything but the cache, which the image rebuild restores |

**Residual risks (hosted):** the hosting provider sees network traffic under its own policy; a listing-driven spike could exhaust the shared api.data.gov limit and make the Scorecard- and FAC-backed tools return rate-limit errors until the hour turns; a user can infer nothing about other users from responses, but the operator could in principle add logging, which the privacy policy commits not to do.
