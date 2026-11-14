# Heron & Hex Higher Ed Data

Ask Claude about U.S. colleges and universities using free public data, with every answer sourced and dated. This plugin bundles six skills and connects to the Heron & Hex hosted connector at `https://mcp.heronhex.com/mcp`. There is nothing to install and no sign-in.

## What you can ask
- "Give me a brief on [college]." A sourced overview that uses every area below, with an optional one-page dashboard.
- "How has fall enrollment at [college] changed over ten years, and who are its closest peers?"
- "Is [college] on heightened cash monitoring, what is its composite score, and what did its last Single Audit find?"
- "Who accredits [college], is its nursing program accredited, and what actions has the agency recorded?"
- "How much research spending does [college] report, and what did NSF and NIH award it?"
- "What do registered nurses earn in [state] or [metro], and how do [college]'s program graduates compare?"

## What the connector does
The connector is one read-only server with 29 tools over public sources: IPEDS and College Scorecard (U.S. Department of Education), Federal Student Aid's public files, the Department of Education's accreditation database (DAPIP), the Federal Audit Clearinghouse, NSF HERD and award data, NIH RePORTER, Grants.gov, SHEEO state finance, WICHE graduate projections, BLS wages and projections, Projections Central and O*NET. Every response names its source, the period it covers and when it was retrieved. Missing data is returned as an explicit null with a reason, never estimated. Identifier matches are exact; name matches are labeled as fuzzy and never guessed when ambiguous.

## What this plugin runs, sends and fetches
- The six skills are Markdown instructions. The `institution-brief` skill also includes one HTML dashboard template that Claude fills with the data you asked for; it makes no network requests and loads no outside scripts, fonts or images.
- The only server this plugin connects to is `https://mcp.heronhex.com/mcp`, operated by Heron & Hex Solutions. It keeps no record of what anyone asks: no access log, no accounts, a cache of public data files only. See the [privacy policy](https://github.com/bsayres/heronhex-highered/blob/main/docs/privacy-policy.md).
- Upstream names, titles and narratives are returned as data and flagged as untrusted; the skills tell Claude to treat them as data, not instructions.

## Install in Claude Code
```
/plugin install heronhex-highered-hosted --marketplace bsayres/heronhex-highered
```
In Claude.ai and Claude Desktop, add the plugin from the directory, or add `https://mcp.heronhex.com/mcp` as a custom connector with no authentication.

## About
Free and open source (MIT) from Heron & Hex Solutions. Source, documentation and the servers themselves: https://github.com/bsayres/heronhex-highered. Questions and bug reports: https://github.com/bsayres/heronhex-highered/issues or mcp-support@heronhex.com. Not an Anthropic product, and provided without warranty. The data comes from public sources and is only as current as each source; confirm anything consequential with the primary source.
