# Security policy

## Reporting a vulnerability
Please do not open a public issue. Use GitHub's private "Report a vulnerability" (Security tab) once the repository is public, or email mcp-support@heronhex.com. Include affected version, reproduction steps, and impact. Expect an acknowledgement within 7 days.

## Scope
Input validation, the outbound-host allowlist, redirect handling, cache path handling, secret handling, and prompt-injection exposure through upstream text. See docs/threat-model.md.

## Not in scope
Vulnerabilities in upstream data services, or inaccurate upstream data.
