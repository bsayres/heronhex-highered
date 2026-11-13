# highered-hosted

One Streamable HTTP endpoint that serves every tool of the five `highered-*` servers, for the Heron & Hex hosted connector. It adds no tools and changes none: the five servers' tool functions are registered as they are. Not published to PyPI; it exists to be built into a container.

## How it differs from running the servers locally
- **One process, one URL, many users.** Stateless Streamable HTTP at `/mcp`; `/healthz` answers `{"status": "ok"}` and nothing else.
- **No request logging.** The HTTP access log is off. Project loggers only ever name an upstream host. Nothing a user sends is written anywhere except the public-data cache keyed by public identifiers (UNITID, year, state).
- **Operator keys.** `COLLEGE_SCORECARD_API_KEY`, `FAC_API_KEY` and `HIGHERED_MCPS_CONTACT` are the operator's and are required at startup. Set `HIGHERED_HOSTED_ALLOW_UNKEYED=1` only for a local trial on api.data.gov's shared demo key.
- **Host check.** `HIGHERED_HOSTED_ALLOWED_HOSTS` (comma-separated public host names) turns on Host and Origin header validation; requests for any other host get 421.
- **Pre-warmed cache.** `highered-hosted-prewarm` loads every bulk file (IPEDS tables, FSA files, DAPIP, HERD, SHEEO, WICHE, BLS, O*NET, crosswalk) into `HIGHERED_MCPS_CACHE`. The Dockerfile runs it at build time, so a fresh container answers warm. Rebuild the image on a schedule (weekly keeps every file inside its TTL) instead of refreshing inside user requests.

## Run locally
```bash
cd servers/highered-hosted
uv sync --no-editable      # editable .pth hooks can be skipped by Python on macOS; re-run after changing any server
HIGHERED_MCPS_CACHE=/tmp/highered-cache HIGHERED_MCPS_CONTACT=you@example.org .venv/bin/highered-hosted-prewarm
HIGHERED_MCPS_CACHE=/tmp/highered-cache HIGHERED_HOSTED_ALLOW_UNKEYED=1 PORT=8080 .venv/bin/highered-hosted
curl -s localhost:8080/healthz
```
Tests: `.venv/bin/python -m pytest -q`.

## Container
```bash
docker build -f servers/highered-hosted/Dockerfile -t heronhex-highered .     # from the repository root
docker run --rm -p 8080:8080 -e HIGHERED_HOSTED_ALLOW_UNKEYED=1 heronhex-highered
```
The build downloads the bulk files once (several minutes) and fails if any of them could not be loaded, so a cold image is never produced.

## Fly.io
`fly.toml` describes one always-on 512 MB machine with a health check on `/healthz`. Secrets go in with `fly secrets set`, never in files. See the repository README for the connector URL and the privacy policy for what the hosted copy does and does not keep.
