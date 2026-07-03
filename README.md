# Dry Run Trading Agent (US Stocks + ETFs)

Local Python project for speculative short-term trading (dry-run only):
- 21:00 build recommendations for the next US trading day
- manual approve/reject per recommendation (Telegram or CLI)
- next day run simulated execution only (no broker orders)
- end-of-day report with PnL, equity update, and monthly target progress

## Risk Profiles (`risk_profile` in `instance/config.json`)

| Profile | Deploy/day | Trades | Position | Daily loss cap | Strategy |
|---------|-----------|--------|----------|----------------|----------|
| `conservative` | 30% | 3 x 10% | SL 3% / TP 6% | 2% | Momentum (MA20) |
| `balanced` | 50% | 3 x ~17% | SL 3% / TP 6% | 3% | Momentum |
| `aggressive` | 100% | 3 x ~34% | SL 3% / TP 6% | 5% | Momentum |
| **`speculative`** | **100%** | **2 x 50%** | **SL 12% / TP 25%** | **50%** | **Volatility + breakout** |

### Speculative mode (current default)

- **Goal:** $1,000 → $2,000/month (`monthly_target_usd` in config)
- **Universe:** Leveraged ETFs (TQQQ, SOXL), crypto-adjacent (MSTR, COIN), high-volatility stocks
- **Scoring:** ATR volatility + volume spike + proximity to 20-day high breakout
- **Heartbeat & reports** include monthly progress and trading days remaining
- **News:** headlines per pick from **Yahoo Finance**, **Google News**, and **Finviz** (deduped, round-robin) + short tone summary in Telegram

## Project layout

```
trading_pulse/              # Python package (code)
  core/ agent/ telegram/ guides/ api/ desktop/
web/static/                 # dashboard UI
instance/                   # local dev: config, secrets, runtime data
  config.example.json       # template → config.json on first run
  .env.example              # template → .env
  data/                     # plans, reports, state (gitignored)
requirements/
  requirements.txt          # pip install -r requirements/requirements.txt
scripts/                    # run_app, run_web, run_scheduler
installer/                  # PyInstaller spec + Windows installer build
tests/
```

**Repo root** keeps only `README.md`, `.gitignore`, and tooling folders — no loose `.py` files.

### Run commands

| What | Command |
|------|---------|
| CLI (plan, approve, …) | `python -m trading_pulse plan` |
| Web dashboard | `python -m trading_pulse.api` or `.\scripts\run_web.ps1` |
| Desktop app | `python -m trading_pulse.desktop` or `.\scripts\run_app.ps1` |
| Scheduler | `python -m trading_pulse run-scheduler` |

**Not in git:** `instance/config.json`, `instance/.env`, `instance/data/`.

Cursor agent conventions: `.cursor/skills/trading-pulse/SKILL.md`.

## Development notes

Before changing Telegram, plans, guides, or watchlist, read **`.cursor/skills/trading-pulse/SKILL.md`**.

### Quick checklist (Telegram / commands)

1. `trading_pulse/agent/dryrun_agent.py` — parse + handler
2. `trading_pulse/telegram/telegram_format.py` — HTML messages + `user_guide_full()`
3. `trading_pulse/telegram/telegram_guide.py` — מדריך טלגרם (`#/guide`)
4. `trading_pulse/telegram/telegram_bot_guide.py` — חיבור בוט (`#/bot-guide`)
5. `trading_pulse/guides/selection_guide.py` — stock selection / watchlist (`#/selection`)
6. Restart app after code changes: `.\scripts\run_app.ps1`

### Dashboard routes

| Page | Route |
|------|-------|
| מדריך טלגרם | `#/guide` |
| חיבור בוט | `#/bot-guide` |
| איך בוחרים מניות | `#/selection` |
| תוכנית פעילה (אישור + חלוקה) | `#/plan` |
| הגדרות + בוט | `#/settings` |

## Setup (Windows PowerShell)

```powershell
cd path\to\investing
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements/requirements.txt
```

## Web Dashboard

Local dashboard with bright UI — equity, recent picks, and a **page per stock** with price charts and invested vs skipped P&L.

```powershell
.\scripts\run_web.ps1
```

Open in browser: **http://127.0.0.1:8765**

- **Dashboard** — equity, monthly progress, recent recommendations
- **Stock page** (e.g. `/stock/SOXL`) — chart per pick, green = you invested, yellow = you skipped + hypothetical result
- **Telegram** (`#/messages`) — full message history (bot + your replies), backfilled from plans/reports

## Windows App (recommended)

Single desktop app: **system tray** + **embedded dashboard window** + **scheduler** (replaces separate task + browser).

```powershell
.\scripts\run_app.ps1
```

- Tray menu: open dashboard, run plan now, heartbeat, quit
- Closing the window hides to tray (agent keeps running)
- Uses Edge WebView2 for the UI (built into Windows 10/11)

Auto-start at logon (no admin):

```powershell
.\scripts\install_app_startup.ps1
```

Remove auto-start:

```powershell
.\scripts\uninstall_app_startup.ps1
```

If you still use the old scheduled task, remove it to avoid duplicate agents:

```powershell
.\scripts\uninstall_task.ps1
```


1) Generate tomorrow plan:

```powershell
python -m trading_pulse plan
```

2) Approve plan (replace date with the generated trading day):

```powershell
python -m trading_pulse approve --day 2026-06-17
```

3) Simulate approved trades for that day:

```powershell
python -m trading_pulse simulate --day 2026-06-17
```

4) Optional scheduler loop:

```powershell
python -m trading_pulse run-scheduler
```

5) Run as a Windows background task (starts at logon, auto-restarts on crash):

```powershell
.\scripts\install_task.ps1
```

If that fails with "Access denied", use Startup folder instead (no admin):

```powershell
.\scripts\install_startup.ps1
```

Check logs:

```powershell
Get-Content .\instance\data\logs\scheduler.log -Tail 30
```

Remove background task / startup shortcut:

```powershell
.\scripts\uninstall_task.ps1
.\scripts\uninstall_startup.ps1
```

## Telegram Integration

1) Create bot with [@BotFather](https://t.me/BotFather) and copy token.
2) Send one message to the bot from your Telegram account.
3) Get your chat id:

```powershell
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates"
```

4) Open `instance/config.json` and set:
- `telegram_bot_token`
- `telegram_chat_id`

5) Generate plan, receive Telegram message, then reply with simple Hebrew (no date needed):

| שלח | פעולה |
|-----|--------|
| `הכל` | לאשר את כל ההמלצות |
| `1,2` | לאשר רק 1 ו-2 |
| `דחה 2` | לדחות רק 2 |
| `סטטוס` | לראות מה מאושר |
| `עזרה` | רשימת פקודות |

Always applies to the **latest plan** you received. Old format with date still works too.

6) Process commands manually (or let scheduler do it every 60 sec):

```powershell
python -m trading_pulse telegram-poll
```

7) Send heartbeat now (manual test):

```powershell
python -m trading_pulse heartbeat
```

Daily heartbeat message is sent automatically at `heartbeat_time` (default `09:00`) and once on service startup.

## Files Created At Runtime

- `instance/config.json` (auto-created on first run; editable times, limits, Telegram fields)
- `instance/data/plans/plan_YYYY-MM-DD.json`
- `instance/data/reports/report_YYYY-MM-DD.json`
- `instance/data/state.json`

## Important

- This is **dry run only**. It does not connect to a broker and does not place real orders.
- Data source is Yahoo Finance via `yfinance`.
