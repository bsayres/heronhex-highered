# Getting started

This guide takes you from nothing to your first answer. No coding is needed, but you will paste a few commands into a terminal.

## What you are installing

Five small programs and six skills that let Claude look up public U.S. higher-education data: enrollment, finances, federal risk flags, accreditation, research funding and program-to-job alignment. The programs run on your own computer and fetch data from federal and state sources. Nothing is sent to Heron & Hex Solutions. See the [privacy policy](privacy-policy.md).

## What you need

1. **Claude Code or Cowork.** The programs run on your computer, so they do not work in Claude.ai chat in a browser or in the mobile apps. For those, a hosted connector (nothing to install) is being set up; see the [README](../README.md#install) for its status.
2. **`uv`**, a free tool that downloads and runs the programs. Install it once.

### Install `uv`

Open a terminal (on Mac: Terminal; on Windows: PowerShell) and paste one command.

Mac or Linux:
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```
(or `brew install uv` if you use Homebrew)

Windows (PowerShell):
```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close the terminal, open a new one, and check it worked:
```
uv --version
```
You should see a version number. If you see "command not found", close and reopen the terminal, or restart Claude so it picks up the new tool.

## Install the plugin

In Claude Code or Cowork, type:
```
/plugin install heronhex-highered --marketplace bsayres/heronhex-highered
```

One install adds all five servers and all six skills.

### Optional keys

Claude Code then asks for three optional values. You can leave all of them blank.

| Value | What it does | Where to get it |
|---|---|---|
| College Scorecard key | Higher request limit for the institutions and labor-market servers | Free at https://api.data.gov/signup |
| FAC key | Higher request limit for Single Audit lookups (risk server) | Free at https://api.data.gov/signup |
| Contact email | Sent to the Bureau of Labor Statistics when you ask for wage data | Any email you are happy to share with BLS |

Without keys, the servers use a shared demo key, which has lower limits. Heavy use or a busy day can produce "rate limit" messages. Adding a free key fixes that.

**In Cowork,** you are not asked for these values, so the shared demo key is used. If you hit limits, use Claude Code with your own keys.

## Check that it works

Start a new conversation and ask:

> Which institutions near [your city] are peers of [your college]?

The first answer can take longer, because `uv` downloads the programs the first time. Later answers are faster.

The skills guide Claude to the right tool, so plain questions work. Some examples:

- "Give me a brief on [college name]." (uses all five servers)
- "Is [college name] on heightened cash monitoring, and what are its recent Single Audit findings?"
- "What is [college name]'s accreditation status, and has anything changed in the last five years?"
- "How has fall enrollment at [college name] changed over the last ten years?"
- "How do graduates of [program] at [college name] earn compared with the national median?"

Every answer lists its sources and dates. Gaps are reported as gaps, not as zero.

## What the answers are and are not

- The data comes from public sources and is only as current as each source (every answer shows the date).
- Claude reports what the tools return. It is told not to score, rank or give a verdict.
- This is not a substitute for the primary source on anything consequential. Confirm there.
- It does not use your institution's internal data, and it does not look up individual people.

## Troubleshooting

| What you see | What to try |
|---|---|
| The tools do not appear | Check you are in Claude Code or Cowork, not Claude.ai chat. Restart Claude after installing. |
| "uv: command not found" or the servers fail to start | Install `uv` (above), then close and reopen the terminal and Claude. |
| First answer is very slow | Normal on first use while `uv` downloads packages. |
| "Rate limit" or "demo key" messages | Get free keys at https://api.data.gov/signup and enter them in Claude Code. |
| A source says "unavailable" | The government site may be down. Try again later; the answer says which source failed. |
| Something else | Open an issue at https://github.com/bsayres/heronhex-highered/issues or email mcp-support@heronhex.com. Please do not include API keys. |

## Remove it

```
/plugin uninstall heronhex-highered
```

## Using Claude Desktop without the plugin

If you only want the servers in Claude Desktop, use the configuration in the [README](../README.md#quick-start-local-path). Servers connected this way do not bring the skills with them.
