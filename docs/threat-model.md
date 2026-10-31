# Threat model (half page)

**Assets:** the user's machine (files, shell), their API keys, the integrity of answers.
**Trust boundary:** the model and user are trusted; every upstream byte (JSON, names, text) is not.

| Threat | Mitigation |
|---|---|
| Prompt injection via upstream text (names, later: audit narratives, grant abstracts) | Text returned only as labeled data fields; static tool descriptions; `notice` field; skills tell the model to treat it as data; no tool takes instructions from data. |
| Malicious or malformed tool input | pydantic types, length caps, strict regex for identifiers, enums for filters; reject, never sanitize; validation runs before any network call. |
| SSRF / data exfiltration through outbound calls | URLs are fixed per source; HTTPS only; host allowlist checked before each request and each redirect hop; no user-supplied URLs; credentials-in-URL rejected. |
| Key leakage | Keys read from env only, sent in headers, never in URLs, logs, errors, fixtures, or the repo; `.env` ignored; gitleaks in CI. |
| Local file abuse | Read-only server; writes only to the cache dir via a name regex plus resolved-path and symlink check; atomic replace; no archives extracted in M1; downloaded data is parsed as JSON only, never executed. |
| Resource exhaustion | Response size caps, timeouts, bounded retries, page cap, per-host pacing. |
| Poisoned or tampered cache | SHA-256 checked on read; mismatch treated as a miss. |
| Supply chain | Lockfile, pip-audit and Dependabot, Actions pinned to commit SHAs, least-privilege workflow permissions, PyPI trusted publishing (OIDC). |
| Personal data | Only needed fields returned; officer/employee and chief-administrator fields dropped; no person-name search. |

**Residual risks:** a compromised upstream can serve false numbers (answers cite sources and dates so users can check); a compromised dependency; the model may still be influenced by text it reads despite labeling.
