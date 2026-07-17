# Cursor / agent tooling for Trading Pulse

## Layers (what to use when)

| Layer | Path | Role |
|-------|------|------|
| **AGENTS.md** | repo root | Always-on map of agents + pipeline |
| **Rules** | `.cursor/rules/*.mdc` | Persistent constraints (secrets, Telegram sync, Python) |
| **Skills** | `.cursor/skills/*/SKILL.md` | On-demand workflows (day review, ship check, conventions) |
| **Subagents** | `.cursor/agents/*.md` | Isolated specialists (cracker, tests, guides, messages, verifier) |
| **Hooks** | `.cursor/hooks.json` | Deterministic guards (session context, dangerous shell) |
| **MCP** | `.cursor/mcp.json` (optional) | External tools (e.g. GitHub) — see example |

## Enable GitHub MCP (optional)

1. Copy `.cursor/mcp.json.example` → `.cursor/mcp.json`
2. Set env var `GITHUB_TOKEN` (PAT with repo scope) in your OS / shell
3. Reload Cursor window
4. Confirm under **Settings → MCP**

Do **not** commit real tokens. Prefer `${env:…}` interpolation.

`gh` CLI already covers most PR/issue work; MCP is optional for richer GitHub tool use.

## Hooks

- `sessionStart` → reminds agents of Trading Pulse tooling
- `beforeShellExecution` → blocks force-push to main / staging `.env`; asks on hard reset
- `afterFileEdit` → marks product edits that still need tests/guides
- `subagentStop` → clears pending when test-writer / guide-updater finish
- `stop` → auto-nudges once to run those specialists if still pending (`loop_limit: 1`)

Requires `python` on PATH (Windows OK). State file: `.cursor/hooks/state/` (gitignored).

## After a feature (short)

Messages → Guides → Tests → Verifier → restart if needed.  
Agents must run test-writer + guide-updater via Task; the stop hook enforces a one-shot reminder.
