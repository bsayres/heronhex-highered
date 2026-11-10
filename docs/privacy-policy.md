# Privacy policy

Last updated: 2026-11-10. Applies to the `heronhex-highered` plugin and the five `highered-*` servers in this repository, published by Heron & Hex Solutions (Byron Sayres).

## What we collect
Nothing. The servers run on your computer. Heron & Hex Solutions operates no server, account system, analytics or telemetry for this software and receives none of your questions, results or settings.

## What runs on your computer
- Each server makes read-only requests to public U.S. government and research data sources, listed below, and returns what they publish.
- Downloaded public files are cached in a local folder (`~/.cache/highered-mcps`, or the folder in `HIGHERED_MCPS_CACHE`). The cache holds public data only. Delete the folder at any time.
- Questions you ask Claude, and the results, are handled by the Claude app you use under Anthropic's terms and privacy policy, not by this software.

## Keys and contact address you may enter
The plugin can ask for a College Scorecard key, a Federal Audit Clearinghouse key (both free from api.data.gov) and a contact email for BLS. They are stored by Claude Code in your system credential store, passed to the servers as environment variables, and not logged, returned in results, or written to the cache.
- The Scorecard key is sent only to `api.data.gov` and the FAC key only to `api.fac.gov`, in request headers.
- The contact email is sent only to `www.bls.gov`, as BLS requests, in the request's User-Agent.

## Hosts contacted
`api.data.gov`, `api.fac.gov`, `educationdata.urban.org`, `nces.ed.gov`, `ope.ed.gov`, `studentaid.gov`, `fsapartners.ed.gov`, `api.nsf.gov`, `ncses.nsf.gov`, `api.grants.gov`, `api.reporter.nih.gov`, `shef.sheeo.org`, `www.wiche.edu`, `www.bls.gov`, `public.projectionscentral.org`, `www.onetcenter.org`. Each server allows only the hosts it needs (see its README). These sites see your IP address and the request, under their own policies.

## Personal data
The tools return institution-level data. They do not search by person name. Some public sources (audit reports, accreditation records) contain organization names and, rarely, names of officials in free text; the tools return only the fields needed and flag such text as untrusted.

## Contact
Questions and support: mcp-support@heronhex.com, or open an issue at https://github.com/bsayres/highered-mcps/issues. Vulnerability reports: see SECURITY.md.
