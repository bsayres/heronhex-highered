# heronhex-highered

Open-source (MIT) MCP servers that let higher-ed leaders, institutional researchers, and analysts ask Claude questions about U.S. institutions using **free public data**. Thin, deterministic wrappers over public sources, no database. Run them on your own computer (bulk files are cached in a local folder), or use the hosted connector: the same code as one server we run, holding a cache of the public files and keeping no record of what anyone asks.

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
**As a plugin (Claude Code and Cowork).** One install brings the five servers and the six skills (the five server skills plus `institution-brief`). The servers run on your computer; Claude.ai chat does not load local servers. The five server packages are on PyPI (`heronhex-*`). New to this? See the [getting-started guide](docs/getting-started.md).
```
/plugin install heronhex-highered --marketplace bsayres/heronhex-highered
```
Claude Code asks for three optional values (a College Scorecard key, a Federal Audit Clearinghouse key, a BLS contact email), stores them in your system credential store, and passes them to the servers as environment variables. Free keys: https://api.data.gov/signup.

**Hosted connector (Claude.ai, Claude Desktop, mobile, or any client that speaks Streamable HTTP).** Address: `https://heronhex-highered.fly.dev/mcp` (`https://mcp.heronhex.com/mcp` once DNS is in place). No sign-in; all tools of the five servers from one URL; add it as a custom connector by URL, or wait for the directory listing, which is pending review. Runs on Fly.io in Ashburn, Virginia (US), built from [`servers/highered-hosted`](servers/highered-hosted); what it does and does not keep is in the [privacy policy](docs/privacy-policy.md#2-the-hosted-connector).

**Servers only (Claude Desktop, or any MCP client).** Use the config below. Connecting a server does not install skills; to add them in Claude Desktop, upload each `SKILL.md` folder as a zip under Settings, Capabilities, Skills. The servers' own instructions and the `institution_brief` prompt work without the skills, but the skills are what make plain questions reach the right tool.

Privacy: [docs/privacy-policy.md](docs/privacy-policy.md).

## Where it works
The plugin runs five small programs on your own computer, so it works in **Claude Code** and **Cowork**. Claude.ai chat in a browser, and the mobile apps, cannot run local programs, so the tools do not appear there even if the plugin is listed in the directory; the hosted connector is for those. You need [`uv`](https://docs.astral.sh/uv/) installed, because the plugin starts each server with `uv run --locked`.

## What this runs and contacts
**What runs.** Five read-only Python servers, the source code that ships inside this plugin under `servers/`. Each starts with `uv run --locked` against its own committed `uv.lock`, so the exact dependency versions are fixed and nothing is fetched from a git branch. The same servers are also published to PyPI for use outside the plugin as `heronhex-institutions`, `heronhex-risk`, `heronhex-accreditation`, `heronhex-funding` and `heronhex-labor`. They have no write tools, and they do not run shell commands, evaluate code or load plugins. They write only to a local cache folder (`~/.cache/highered-mcps`, or the folder in `HIGHERED_MCPS_CACHE`). The six skills are Markdown instructions. The `institution-brief` skill also includes one HTML dashboard template, which Claude fills with data you ask for; it makes no network requests and loads no outside scripts, fonts or images.

**What they contact.** Only these public sources, over HTTPS, with each server allowed to reach only its own hosts. The allowlist is enforced in code and checked on every redirect.

| Server | Hosts | Used for |
|---|---|---|
| institutions | `educationdata.urban.org`, `nces.ed.gov`, `api.data.gov` | IPEDS directory, enrollment, finance and retention; College Scorecard |
| risk | `studentaid.gov`, `fsapartners.ed.gov`, `api.fac.gov` | Heightened Cash Monitoring, composite scores, default rates; Single Audit findings |
| accreditation | `ope.ed.gov` | Department of Education accreditation database (DAPIP) |
| funding | `api.nsf.gov`, `ncses.nsf.gov`, `api.grants.gov`, `api.reporter.nih.gov`, `shef.sheeo.org`, `www.wiche.edu` | Research spending and awards, funding opportunities, state funding, enrollment projections |
| labor-market | `www.bls.gov`, `public.projectionscentral.org`, `www.onetcenter.org`, `api.data.gov`, `nces.ed.gov` | Wages and occupation outlook, state projections, O*NET skills, Scorecard program data |

**Keys and your email.** The plugin asks for three optional values and stores them in your system credential store. The College Scorecard key goes only to `api.data.gov`, and the audit key only to `api.fac.gov`, in request headers. The contact email goes only to `www.bls.gov`, as BLS asks for bulk files. None of them is logged, returned in results or written to the cache. The servers read them from three environment variables (`COLLEGE_SCORECARD_API_KEY`, `FAC_API_KEY`, `HIGHERED_MCPS_CONTACT`) that Claude Code fills from the plugin's own settings; the code reads no other credential from your machine. Each value defaults to empty, so the servers also run with no keys, on the shared demo keys, which are quickly rate limited. Cowork does not prompt for plugin settings, so there the servers use the demo keys; Claude Code prompts for them.

**What we collect.** Nothing from the plugin: no server, account or analytics is involved. The hosted connector relays your tool calls to the public sources and keeps no record of them (no access log, no accounts, a cache of public files only). See the [privacy policy](docs/privacy-policy.md).

**Untrusted text.** Names, program titles and audit narratives come from public sources and could contain text written to look like instructions. The servers return them as data and flag them as untrusted, and the skills tell Claude not to follow them. See [docs/threat-model.md](docs/threat-model.md).

## Quick start (local path)
```bash
cp .env.example .env            # add your free College Scorecard key
uvx --from ./servers/highered-institutions highered-institutions
```
Claude Desktop / Claude Code config:
```json
{"mcpServers": {"highered-institutions": {
  "command": "uvx",
  "args": ["--from", "/absolute/path/to/heronhex-highered/servers/highered-institutions", "highered-institutions"],
  "env": {"COLLEGE_SCORECARD_API_KEY": "your-free-key"}
}}}
```

## Using alongside 1102tools servers
See [docs/using-with-1102tools.md](docs/using-with-1102tools.md) (SAM.gov, USAspending, BLS OEWS).

## Docs
[docs/getting-started.md](docs/getting-started.md) (install and first questions, step by step) · [docs/sources.md](docs/sources.md) (what was verified, what was not) · [PLAN.md](PLAN.md) · [SECURITY.md](SECURITY.md) · [CONTRIBUTING.md](CONTRIBUTING.md)

## About
Built and maintained by Heron & Hex Solutions. Free and open source (MIT). Not an Anthropic product, and provided without warranty.

## Support
Questions and bug reports: [GitHub Issues](https://github.com/bsayres/heronhex-highered/issues). Anything private: mcp-support@heronhex.com.

## License
MIT. Data licenses differ by source; each response names its source. IPEDS via the Urban Institute is ODC-By 1.0.
