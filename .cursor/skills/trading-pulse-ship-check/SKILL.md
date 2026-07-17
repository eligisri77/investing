---
name: trading-pulse-ship-check
description: >-
  Pre-done shipping checklist for Trading Pulse features. Use before telling the
  user a change is finished, or when asked to double-check tests, guides,
  messages, and restart needs.
---

# Trading Pulse — Ship check

Run before declaring a feature/fix done.

## Checklist

```
Ship check
- [ ] Behavior implemented (minimal diff)
- [ ] User-facing copy updated (`telegram_format` / @trading-pulse-bot-messages)
- [ ] Guides updated if commands/flow changed (@trading-pulse-guide-updater)
- [ ] Tests added/updated (@trading-pulse-test-writer)
- [ ] Focused pytest green
- [ ] No secrets in diff (instance/.env, tokens)
- [ ] Restart noted if needed: .\scripts\run_app.ps1
```

## Delegate order (do not skip 2–3 after product/UX edits)

1. `@trading-pulse-bot-messages` (if text)
2. `@trading-pulse-guide-updater` — **required** for commands/flow/UX
3. `@trading-pulse-test-writer` — **required** for behavior changes
4. `@trading-pulse-verifier`

If you forget, the project `stop` hook sends one automatic follow-up.

## Report to user

Short: what changed · tests · restart yes/no · anything left open.
