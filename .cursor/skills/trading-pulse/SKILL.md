---
name: trading-pulse
description: >-
  Trading Pulse (dry-run trading agent) project conventions: Telegram two-step
  flow, HTML messages, dashboard guides, ticker watchlist, plan notifications.
  Use when editing trading_pulse/agent/dryrun_agent.py, trading_pulse/telegram/*,
  web/static, trading_pulse/desktop/win_app.py, adding Telegram commands/messages,
  or updating guide/selection pages.
---

# Trading Pulse — Agent Conventions

Read this skill before changing Telegram, plans, guides, or watchlist behavior.

## Architecture (key files)

| Area | Files |
|------|--------|
| Agent + scheduler + Telegram poll | `trading_pulse/agent/dryrun_agent.py` |
| Message HTML + user guides | `trading_pulse/telegram/telegram_format.py` |
| Table/chart images | `trading_pulse/telegram/telegram_images.py` |
| Capital allocation (שלב 2) | `trading_pulse/agent/capital_allocation.py` |
| Watchlist add/remove/discover | `trading_pulse/agent/ticker_manager.py` |
| Dashboard API | `trading_pulse/api/web_app.py` |
| Dashboard UI | `web/static/app.js`, `style.css` |
| Telegram help content | `telegram_guide.py` → `/api/telegram/guide` → `#/guide` |
| Stock selection help | `guides/selection_guide.py` → `/api/selection/guide` → `#/selection` |
| Settings UI | `core/app_settings.py` → `/api/settings` → `#/settings` |
| Config | `config.json` (secrets in `.env`) |
| Desktop app | `desktop/win_app.py`, `scripts/run_app.ps1` |

Paths are under `trading_pulse/` unless noted. Entry: `python -m trading_pulse`, `python -m trading_pulse.api`, `python -m trading_pulse.desktop`.

## Plan lifecycle (broker-style)

Module: `trading_pulse/agent/plan_engine.py`

| Status | Meaning |
|--------|---------|
| `draft` | Evening research — awaiting user confirm |
| `confirmed` | Order placed — fills at market open |
| `executed` | Filled at open |
| `closed` | EOD report done |
| `superseded` | Replaced by newer evening plan |

**Evening (~20:15 UTC)** — fresh scan from current portfolio; supersedes stale plans  
**Confirm** — one step (`הכל` / אשר הזמנה): approve + equal split  
**Morning (~13:35 UTC)** — fill confirmed orders at open price  
**Evening (~20:20 UTC)** — EOD report, plan → `closed`

Locked only when `confirmed` + pending buys + before market open.  
Holding all picks already → evening regenerates.

## Telegram: simplified user flow

**ערב (~20:15 UTC)** — תוכנית למחר + `הכל` לאישור (חלוקה אוטומטית)  
**בוקר (~13:35 UTC)** — כניסה במחיר פתיחה + הודעה  
**ערב (~20:20 UTC)** — דוח יומי (ממומש + עתידי)

**יום ראשון:** `הכל` מחלק $1,000 על ~3 מניות (`initial_deploy_stocks`)  
**מניה חדשה בלי מזומן:** `מכור SYMBOL` / `החלף X Y` → אז `הכל`  
**חלוקה ידנית (מתקדם):** `ח1`…`ח5` רק אם נשלחה הודעת חלוקה ידנית

Parser: `parse_telegram_user_command()` in `dryrun_agent.py`.  
Flow helpers: `trading_flow.py` (`plan_intent`, `auto_allocate_equal`, `funding_gap`).

## Telegram messages: rules

- **All user-facing Telegram text**: HTML via `parse_mode="HTML"`.
- Escape dynamic text with `telegram_format.escape_html()`.
- Photo captions: HTML + fallback strip tags in `send_telegram_photo()`.
- App inbox (`notification_mode=app|both`): strip HTML for `app_notify` log.

### Plan notifications bundle

Use `send_plan_notifications(cfg, plan)` — not raw `send_user_notification` alone:

1. Summary text (`format_plan_message` → `telegram_format.format_plan`)
2. Table image (`send_plan_table_image`)
3. Per-stock chart + caption (`send_plan_stock_charts`)

`generate_plan()` reloads tickers from `ticker_manager.list_tickers()` — no restart needed after watchlist changes.

## Checklist: new Telegram command or message type

When adding or changing a Telegram command/reply:

- [ ] `parse_telegram_user_command()` — new `kind` + patterns (before approve fallback)
- [ ] `process_telegram_commands()` — handler branch, `parse_mode="HTML"`
- [ ] `telegram_format.py` — HTML helpers if reusable
- [ ] **`telegram_guide.py`** — add to `commands` section (מדריך טלגרם)
- [ ] **`telegram_bot_guide.py`** — if bot setup / settings UX changes
- [ ] **`telegram_format.user_guide_full()`** — if it's a common command
- [ ] **`selection_guide.py`** — only if it affects how stocks are picked/scanned
- [ ] **`web/static/app.js`** — only if dashboard needs new route/UI
- [ ] **`win_app.py`** tray — optional menu + `location.hash`

## Checklist: new watchlist / ticker feature

- [ ] Logic in `ticker_manager.py` (persist `config.json` tickers)
- [ ] Telegram parse + handler in `dryrun_agent.py`
- [ ] `telegram_guide.py` + `selection_guide.py` (pipeline step 1 mentions watchlist)
- [ ] `generate_plan()` already reloads tickers — verify if other code caches `cfg.tickers`

## Dashboard guide pages

| Route | API | Content module |
|-------|-----|----------------|
| `#/guide` | `GET /api/telegram/guide` | `telegram_guide.py` |
| `#/bot-guide` | `GET /api/telegram/bot-guide` | `telegram_bot_guide.py` |
| `#/selection` | `GET /api/selection/guide` | `selection_guide.py` (uses live `config.json`) |
| `#/plan` | `GET /api/plan/active`, allocation API | `web/static/app.js` |
| `#/settings` | `GET/PUT /api/settings`, telegram | `app_settings.py`, `telegram_settings.py` |

Nav links in `renderNav()` in `app.js`. Reuse `.guide-*` CSS classes.

## Hebrew UX patterns

- User guides: `user_guide_step1()`, `user_guide_step2()`, `user_guide_done()` in `telegram_format.py`
- Status/allocation replies show contextual "מה לשלוח עכשיו"
- Plan summary is short; per-stock detail in separate photo messages

## Runtime notes

- Restart app after code changes: `.\scripts\run_app.ps1` (quit tray first)
- `telegram_poll_interval_sec` reloads from config within ~1 min (no restart)
- Schedule times (`plan_reminder_time`, etc.) need restart
- `notification_mode`: `app` | `telegram` | `both`
- Single instance lock — don't run duplicate schedulers

## Do not

- Commit `.env`, tokens, or filled `telegram_bot_token` in config
- Use plain text Telegram replies without HTML attempt
- Add approve parsing for non-numeric free text (caused `תוכנית עכשיו` bug)
- Forget guide updates when user-facing commands change

## More detail

See [reference.md](reference.md) for command inventory and plan flow diagram.
