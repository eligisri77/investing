---
name: trading-pulse-day-review
description: >-
  Review a Trading Pulse trading day from plans, reports, state, scheduler
  logs, and Telegram inbox. Use when the user asks what happened today/yesterday,
  to explain buys/sells/skips, Method 2 fills, message UX issues, or portfolio
  vs equity mismatches. Complements the trading-pulse-cracker subagent.
---

# Trading Pulse — Day Review

Read-only forensic checklist for one US session day `D` (ISO `YYYY-MM-DD`).

## When to use

- «מה קרה היום?» / «למה נקנה/נמכר X?» / «עבור על הלוגים»
- Comparing Telegram messages to actual fills
- Checking Method 2 pending vs filled vs invalidated

## Evidence map

Dev root: `instance/data/` (installed: `%LOCALAPPDATA%\TradingPulse\data\`).

| Need | File |
|------|------|
| Positions + equity | `state.json` |
| Evening plan for session D | `plans/plan_D.json` |
| EOD report for session D | `reports/report_D.json` |
| Jobs / skips | `logs/scheduler.log` (filter by date / `JOB`) |
| What user saw | `telegram/messages.json` (`context`: plan, entry, intraday, report, reply:*) |
| Process alive | `health.json` |

Related plan for **morning of D** was usually generated the **previous calendar evening** with `for_trading_day: D`.

## Checklist

Copy and tick:

```
Day review D=____
- [ ] state.json — open_positions, equity, cash
- [ ] plan_D — recs, holding_actions, approved/allocated, method2_status
- [ ] report_D — pnl, unrealized, executed, held_eod
- [ ] messages.json — plan / entry / intraday / sell replies
- [ ] scheduler.log — entry, intraday, plan, report jobs
- [ ] Explain gaps (skipped entry, no breakout, manual swap)
```

## Common “gotchas”

| Symptom | Likely cause |
|---------|----------------|
| Entry job silent / “no buys” | Full book or no approved new buys; morning should notify via `format_no_entries_morning` |
| Method 2 not bought at open | By design — waits for breakout (`pending_breakout`) |
| Equity flat while stock up | Unrealized not booked until sell |
| User sold via Telegram | Look for `reply:` / portfolio messages; state updated outside evening plan |
| «הכל» didn’t swap | `הכל` = cash buys only; need `החלף` / `מכור` |

## Message UX expectations (post Jul-2026)

- Plan / app text: same clarity as Telegram (`format_plan` → app via `format_plan_message_for_app` + strip HTML)
- Intraday suggestions: explicit `✅ איך לבצע:` + copy-paste command
- Empty morning entry: short “אין קניות היום” ping

## Report template

Use the same sections as `.cursor/agents/trading-pulse-cracker.md` (סיכום → ציר זמן → תיק → למה → האם תקין).

## Do not

- Dump secrets from `.env`
- Change code during a pure review (list fix ideas separately)
- Confuse Israel clock with US session date
- During selection freeze (~until 2026-08-28): do not propose implementing Method2/score filters unless the user asks — append observations to `.cursor/learnings/selection-insights.md` instead
