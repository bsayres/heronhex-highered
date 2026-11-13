# Privacy policy

Last updated: 2026-11-13. Applies to the `heronhex-highered` plugin, the five `highered-*` servers in this repository, and the hosted connector built from them, all published by Heron & Hex Solutions (Byron Sayres).

There are two ways to use this software. They differ in what we can see, so they are described separately.

## 1. The plugin and the servers on your own computer

**What we collect: nothing.** The servers run on your computer. Heron & Hex Solutions operates no account system, analytics or telemetry for this software and receives none of your questions, results or settings.

- Each server makes read-only requests to the public U.S. government and research data sources listed below and returns what they publish.
- Downloaded public files are cached in a local folder (`~/.cache/highered-mcps`, or the folder in `HIGHERED_MCPS_CACHE`). The cache holds public data only. Delete the folder at any time.
- Questions you ask Claude, and the results, are handled by the Claude app you use under Anthropic's terms and privacy policy, not by this software.

**Keys and contact address you may enter.** The plugin can ask for a College Scorecard key, a Federal Audit Clearinghouse key (both free from api.data.gov) and a contact email for BLS. They are stored by Claude Code in your system credential store, passed to the servers as environment variables, and not logged, returned in results, or written to the cache. The Scorecard key is sent only to `api.data.gov` and the FAC key only to `api.fac.gov`, in request headers. The contact email is sent only to `www.bls.gov`, as BLS requests, in the request's User-Agent.

## 2. The hosted connector

The hosted connector is the same five servers running as one process on a server we operate, so that Claude.ai, Claude Desktop and the mobile apps can use them without installing anything. When you use it, your requests pass through our server.

**What our server sees.** Each tool call: the tool name and its arguments (an institution identifier or name, a state, an occupation or program code, a date range) and the network address and headers your client sends.

**What we keep: no request content.** The server writes no access log and no record of tool calls, arguments or results. It logs only startup problems and the name of an upstream site it could not reach. It holds no accounts and sets no cookies.

**What it stores.** A cache of the public bulk files the tools need (IPEDS tables, FSA lists, the DAPIP file, HERD, SHEEO, WICHE, BLS and O*NET files), built when the server image is built and refreshed on a schedule. Single-institution rows fetched on demand are cached by public identifier for up to a day. The cache contains public data only and nothing that identifies a user.

**Keys.** The hosted server uses Heron & Hex Solutions' own api.data.gov keys and contact address. You do not enter any. They are sent only to `api.data.gov`, `api.fac.gov` and `www.bls.gov` as described above.

**Where it runs.** On a hosting provider's server in the United States. The provider sees the network traffic to and from the server under its own policies. The connector's address, the provider and the region are listed in the repository README.

**Upstream sites.** Requests to the public data sources come from our server's address, not yours, so those sites do not see you.

## Hosts contacted (both modes)
`api.data.gov`, `api.fac.gov`, `educationdata.urban.org`, `nces.ed.gov`, `ope.ed.gov`, `studentaid.gov`, `fsapartners.ed.gov`, `api.nsf.gov`, `ncses.nsf.gov`, `api.grants.gov`, `api.reporter.nih.gov`, `shef.sheeo.org`, `www.wiche.edu`, `www.bls.gov`, `public.projectionscentral.org`, `www.onetcenter.org`. Each server allows only the hosts it needs (see its README). In local mode these sites see your IP address and the request, under their own policies.

## Personal data
The tools return institution-level data. They do not search by person name. Some public sources (audit reports, accreditation records) contain organization names and, rarely, names of officials in free text; the tools return only the fields needed and flag such text as untrusted.

## Contact
Questions and support: mcp-support@heronhex.com, or open an issue at https://github.com/bsayres/heronhex-highered/issues. Vulnerability reports: see SECURITY.md.
