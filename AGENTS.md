# Trading Pulse — Agent guide

Dry-run swing trading agent (Telegram + desktop dashboard). Package: `trading_pulse/`.

## Start here

| Need | Open / invoke |
|------|----------------|
| Tooling overview | `.cursor/README.md` |
| Conventions | `.cursor/skills/trading-pulse/SKILL.md` |
| Day / “what happened?” | `trading-pulse-day-review` + `@trading-pulse-cracker` |
| Pre-done checklist | skill `trading-pulse-ship-check` |
| Bot copy | `@trading-pulse-bot-messages` |
| App guides | `@trading-pulse-guide-updater` |
| Tests for new code | `@trading-pulse-test-writer` |
| Verify | `@trading-pulse-verifier` |

## Feature pipeline

1. Implement (main agent)
2. `@trading-pulse-bot-messages` — if user-facing text
3. `@trading-pulse-guide-updater` — if commands / flow
4. `@trading-pulse-test-writer` — cover behavior
5. `@trading-pulse-verifier` — green tests + gaps
6. Restart if needed: `.\scripts\run_app.ps1`

## Layout

```
trading_pulse/   agent, telegram, api, desktop, core, guides
instance/        writable runtime (config, plans, reports, logs)
web/static/      dashboard UI
tests/           pytest
.cursor/         agents, skills, rules, hooks, mcp example
```

Dev data: `instance/data/`. Installed: `%LOCALAPPDATA%\TradingPulse\`.

## Hard rules

- Never commit `.env` / bot tokens
- User-facing Telegram = HTML
- Prefer small diffs

## Optional MCP

Copy `.cursor/mcp.json.example` → `.cursor/mcp.json` and set `GITHUB_TOKEN` if you want GitHub MCP. See `.cursor/README.md`.
