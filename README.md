# highered-mcps

Open-source (MIT) MCP servers that let higher-ed leaders, institutional researchers, and analysts ask Claude questions about U.S. institutions using **free public data**. Thin, deterministic wrappers over public sources. No hosted data and no database: bulk files are downloaded on demand into a local cache folder on your machine.

Modeled on [1102tools/federal-contracting-mcps](https://github.com/1102tools/federal-contracting-mcps) (not a fork).

| Server | Status | Question it answers |
|---|---|---|
| [`highered-institutions`](servers/highered-institutions) | Milestone 1, built | "Show the enrollment trend for [institution] and its closest peers." |
| `highered-risk` | Milestone 2, planned | Title IV financial responsibility, audit findings |
| `highered-funding` | Milestone 3, planned | Research spend, grants, state funding, enrollment outlook |

## Principles
- Every response carries `source`, `source_url`, `as_of` (dataset period), and `retrieved_at`.
- Missing data is an explicit `null` with a reason. Nothing is estimated or filled.
- Identifier matches are exact; name matches are labeled fuzzy and never guessed when ambiguous.
- Read-only. Network calls only to the hosts listed in each server's README, enforced in code.
- Upstream free text is untrusted data. See [docs/threat-model.md](docs/threat-model.md).

## Quick start (local path)
```bash
cp .env.example .env            # add your free College Scorecard key
uvx --from ./servers/highered-institutions highered-institutions
```
Claude Desktop / Claude Code config:
```json
{"mcpServers": {"highered-institutions": {
  "command": "uvx",
  "args": ["--from", "/absolute/path/to/highered-mcps/servers/highered-institutions", "highered-institutions"],
  "env": {"COLLEGE_SCORECARD_API_KEY": "your-free-key"}
}}}
```

## Using alongside 1102tools servers
See [docs/using-with-1102tools.md](docs/using-with-1102tools.md) (SAM.gov, USAspending, BLS OEWS).

## Docs
[docs/sources.md](docs/sources.md) (what was verified, what was not) · [PLAN.md](PLAN.md) · [SECURITY.md](SECURITY.md) · [CONTRIBUTING.md](CONTRIBUTING.md)

## License
MIT. Data licenses differ by source; each response names its source. ProPublica data must be credited to ProPublica; IPEDS via the Urban Institute is ODC-By 1.0.
