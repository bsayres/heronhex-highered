# highered-mcps

Open-source (MIT) MCP servers that let higher-ed leaders, institutional researchers, and analysts ask Claude questions about U.S. institutions using **free public data**. Thin, deterministic wrappers over public sources. No hosted data and no database: bulk files are downloaded on demand into a local cache folder on your machine.

| Server (PyPI package) | Status | Question it answers |
|---|---|---|
| [`highered-institutions`](servers/highered-institutions) (`heronhex-institutions`) | Milestone 1 built (plus financial snapshot) | "Show the enrollment trend for [institution] and its closest peers." |
| [`highered-risk`](servers/highered-risk) (`heronhex-risk`) | Milestone 2 built (FSA status, audit findings) | Title IV risk signals |
| [`highered-funding`](servers/highered-funding) (`heronhex-funding`) | Milestone 3 built | Research spend, federal awards and opportunities, state funding, graduate projections |
| [`highered-labor-market`](servers/highered-labor-market) (`heronhex-labor`) | Milestones 4 and 5 built | Do programs line up with national and state labor-market demand? |
| [`highered-accreditation`](servers/highered-accreditation) (`heronhex-accreditation`) | Milestone 6 built | Is the institution, or a program such as nursing, accredited now, and what actions has an agency recorded? |

## Principles
- Every response carries `source`, `source_url`, `as_of` (dataset period), and `retrieved_at`.
- Missing data is an explicit `null` with a reason. Nothing is estimated or filled.
- Identifier matches are exact; name matches are labeled fuzzy and never guessed when ambiguous.
- Read-only. Network calls only to the hosts listed in each server's README, enforced in code.
- Upstream free text is untrusted data. See [docs/threat-model.md](docs/threat-model.md).

## Install
**As a plugin (Claude Code and Cowork).** One install brings the five servers and the six skills (the five server skills plus `institution-brief`). The servers run on your computer; Claude.ai chat does not load local servers. Not yet published: this needs the PyPI release and a public repo first.
```
/plugin install heronhex-highered --marketplace <owner>/<repo>
```
Claude Code asks for three optional values (a College Scorecard key, a Federal Audit Clearinghouse key, a BLS contact email), stores them in your system credential store, and passes them to the servers as environment variables. Free keys: https://api.data.gov/signup.

**Servers only (Claude Desktop, or any MCP client).** Use the config below. Connecting a server does not install skills; to add them in Claude Desktop, upload each `SKILL.md` folder as a zip under Settings, Capabilities, Skills. The servers' own instructions and the `institution_brief` prompt work without the skills, but the skills are what make plain questions reach the right tool.

Privacy: [docs/privacy-policy.md](docs/privacy-policy.md).

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
MIT. Data licenses differ by source; each response names its source. IPEDS via the Urban Institute is ODC-By 1.0.
