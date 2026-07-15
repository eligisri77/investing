# Trading Pulse — Agent guide

Dry-run swing trading agent (Telegram + desktop dashboard). Package: `trading_pulse/`.

## Start here

| Need | Open / invoke |
|------|----------------|
| Conventions (Telegram, plans, guides) | `.cursor/skills/trading-pulse/SKILL.md` |
| Day / log / “what happened?” | skill `trading-pulse-day-review` + `@trading-pulse-cracker` |
| Write tests for new code | `@trading-pulse-test-writer` |
| Update app / dashboard guides | `@trading-pulse-guide-updater` |
| Update bot / notification copy | `@trading-pulse-bot-messages` |
| Verify after a change | `@trading-pulse-verifier` |

## Suggested pipeline after a feature

1. Implement (main agent)
2. `@trading-pulse-bot-messages` — if user-facing text changed
3. `@trading-pulse-guide-updater` — if commands / flow / selection changed
4. `@trading-pulse-test-writer` — cover new behavior
5. `@trading-pulse-verifier` — run tests + gap check

## Layout

```
trading_pulse/
  agent/       dryrun_agent, positions, intraday, method2, plan_engine
  telegram/    format, images, notify, guides
  api/         FastAPI dashboard
  desktop/     Windows tray app
  core/        paths, config, bootstrap
instance/      writable runtime (config, plans, reports, logs, inbox)
web/static/    dashboard UI
tests/         pytest
```

Dev data: `instance/data/`. Installed: `%LOCALAPPDATA%\TradingPulse\`.

## Daily cycle (UTC config times)

1. Evening plan → user confirms (`הכל` / swaps manual)
2. Morning entry at open (+ Method 2 pending breakout)
3. Intraday monitor (alerts + suggestions with how-to commands)
4. EOD report (realized + unrealized)

## Hard rules

- Never commit `.env` / bot tokens
- User-facing Telegram = HTML
- Prefer small diffs; restart app after code changes: `.\scripts\run_app.ps1`
