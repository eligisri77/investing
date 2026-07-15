# Trading Pulse — Reference

## Telegram commands (inventory)

### שלב 1 — אישור
`הכל`, `1,2,3`, `דחה 4`, `approve`, `reject`

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
| intraday | HTML — alerts + suggestions with `איך לבצע` commands |
| allocation:prompt | HTML |
| reminder:pre_sim | HTML (~22:00 if pending) |
| report | HTML + table PNG |
| heartbeat | HTML |
| reply:portfolio | photo + HTML caption |

## Plan generation flow

```
generate_plan()
  → fetch_signal_universe(tickers from config)
  → filter held symbols, rank by score
  → top N → enrich (news, sentiment, backtest)
  → save plan_YYYY-MM-DD.json (status: pending_approval)
```

User approves → allocation prompt → simulation at market_close_sim_time.

## Config fields agents often touch

`risk_profile`, `tickers`, `signal_sources`, `notification_mode`, `telegram_poll_interval_sec`, `plan_reminder_time`, `hold_mode`, `max_hold_days`, `max_open_positions`, `planning_time`, `market_close_sim_time`

Editable via dashboard `#/settings`. Telegram secrets via `#/settings` bot section → `.env`.

Installed app user data: `%LOCALAPPDATA%\TradingPulse\`.
