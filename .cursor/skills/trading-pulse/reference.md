# Trading Pulse — Reference

## Telegram commands (inventory)

### שלב 1 — אישור
`הכל`, `1,2,3`, `דחה 4`, `approve`, `reject`

### הצעת קנייה (אחת-אחת, `offer_queue.py`)
`כן` (buy at suggested amount), an amount like `150`/`$150` (buy custom amount), `דלג` (skip),
or `החלף FROM TO` when TO is the current offer (counts as accept + advances) —
only consumed as an offer answer when a pending offer exists (`try_resolve_pending_offer` /
`consume_offer_after_manual_swap`); direct commands (`מכור`, `קנה SYMBOL`, `תיק`, `סטטוס`, ...)
still work at any time. Pre-market `החלף` sells now and approves the buy for open
(«אושרה לקנייה בפתיחה») — does **not** open שלב 2 / ח1…ח5. At market-open cutoff,
already-approved symbols (including via `החלף`) stay approved; only unanswered are «לא נענו».

### שלב 2 — חלוקה
`ח1`…`ח5`, `חלוקה`

### כללי
| Command | kind |
|---------|------|
| `סטטוס`, `מצב` | status |
| `תיק` | portfolio |
| `עזרה` | help |
| `מדריך` | guide_telegram (full guide) |
| `איך בוחרים מניות` | guide_selection |
| `חיבור בוט` | guide_bot_setup |
| `תוכנית` | plan_show (resend) |
| `תוכנית עכשיו` | plan_now (generate) |
| `מניות` | tickers_list |
| `הוסף SYM` / `add SYM` | ticker_add |
| `הסר SYM` / `remove SYM` | ticker_remove |
| `חפש מניות` | tickers_discover |

Bare `1`–`5` during pending allocation → allocation pick (with hint).

## Dashboard pages

| Route | Content |
|-------|---------|
| `#/plan` | Approve/reject + allocation ח1…ח5 |
| `#/guide` | Telegram command guide |
| `#/bot-guide` | Create & connect Telegram bot |
| `#/selection` | How stocks are picked |
| `#/settings` | Config + bot token/chat id |

## Outgoing message types

| Context | Format |
|---------|--------|
| plan | HTML text + table PNG + per-stock chart PNGs |
| entry | HTML — fills and/or Method 2 pending; empty morning → `format_no_entries_morning` |
| portfolio_review | HTML — day 2+ digest (`format_portfolio_review_digest`): holding actions + idle-cash advice, at `portfolio_review_time` (Israel) |
| portfolio_review:intro | HTML — short "🔎 סריקת שוק מלאה" intro, empty-portfolio days only (before the day's first offer) |
| portfolio_review:no_picks | HTML — empty-portfolio day, full scan ran but nothing qualified (`no_picks_reason`) — never stay silent |
| offer | photo (chart, `offer:{symbol}`) + photo (metric cubes, `offer:cubes:{symbol}`) + short HTML «הצעה N/M» action strip (cash, כן/סכום/דלג) — no free-form explanation wall |
| offer:decision | HTML — one-line ack after a `כן`/amount/`דלג` reply |
| offer:nudge | HTML — one-time "⏳ עדיין מחכה לתשובה" after ~10 min silence |
| offer:cutoff | HTML — "⏰ השוק נפתח" when the queue is still unanswered at market open |
| offer:done | HTML — wrap-up once the offer queue is empty (bought list or "לא נקנה כלום") |
| intraday | HTML — alerts + suggestions with `איך לבצע` commands; also idle-cash top-up (`תקנה SYMBOL`) when the book is full (`intraday_cash_topup_min_usd`) |
| allocation:prompt | HTML |
| report | HTML + table PNG |
| heartbeat | HTML |
| reply:portfolio | photo + HTML caption |

Removed: `cash_reminder` context and the once-daily cash reminder job/config/module — folded into `portfolio_review` (pre-market) and `intraday` (idle-cash top-up, market hours).

## Plan generation flow

```
generate_plan()
  → fetch_signal_universe(tickers from config)
  → filter held symbols, rank by score
  → top N → enrich (news, sentiment, backtest)
  → save plan_YYYY-MM-DD.json (status: pending_approval)
```

User answers offers (or sends `הכל`) → cash allocation → entry fills at `entry_sim_time` (next open) → idle-cash top-up suggestions during intraday checks (`intraday_cash_topup_min_usd`, market hours) → daily report at `market_close_sim_time`.

## Config fields agents often touch

`risk_profile`, `tickers`, `signal_sources`, `notification_mode`, `telegram_poll_interval_sec`, `hold_mode`, `max_hold_days`, `max_open_positions`, `portfolio_review_time` (Israel), `entry_sim_time`, `market_close_sim_time`, `intraday_cash_topup_min_usd`

Unused legacy keys (kept for compat only): `planning_time`, `plan_reminder_time`, `cash_reminder_time`.

Editable via dashboard `#/settings`. Telegram secrets via `#/settings` bot section → `.env`.

Installed app user data: `%LOCALAPPDATA%\TradingPulse\`.
