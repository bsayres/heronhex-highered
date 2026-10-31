# Using with 1102tools servers

[1102tools](https://github.com/1102tools/federal-contracting-mcps) publishes MCP servers for federal data. Install them separately; these servers do not depend on them.

- **SAM.gov** (entity search, exclusions): take the `ueis` from `resolve_institution` or `get_institution_profile` and look the UEI up for registration status and exclusions.
- **USAspending**: use the same UEI to find federal awards and subawards to the institution. Remember a UEI in IPEDS may belong to a system office rather than a single campus.
- **BLS OEWS**: for regional wage benchmarks, use the institution's state and metro (CBSA) from the profile.

Typical flow: `resolve_institution` -> UEI/EIN -> 1102tools servers -> cite each source and its as-of date.
