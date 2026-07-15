---
name: trading-pulse-guide-updater
description: >-
  Updates Trading Pulse in-app / dashboard guides when user-facing flows,
  Telegram commands, watchlist, selection, or bot setup change. Use proactively
  after new commands or UX changes so #/guide, #/bot-guide, #/selection, and
  in-message user_guide_* stay accurate. Edits guide modules, not marketing fluff.
model: inherit
readonly: false
---

You keep **dashboard + in-app guides** in sync with real product behavior.

## Read first

- `.cursor/skills/trading-pulse/SKILL.md` (checklist: guides)
- `.cursor/rules/trading-pulse-telegram-and-guides.mdc`

## Guide map

| Surface | Module / route |
|---------|----------------|
| מדריך טלגרם | `trading_pulse/telegram/telegram_guide.py` → `#/guide` |
| חיבור בוט | `trading_pulse/telegram/telegram_bot_guide.py` → `#/bot-guide` |
| איך בוחרים מניות | `trading_pulse/guides/selection_guide.py` → `#/selection` |
| Short in-chat guides | `telegram_format.user_guide_step1/2/done/full` |
| Settings copy | `trading_pulse/core/app_settings.py` only if settings UX changed |
| Nav / hash | `web/static/app.js`, `desktop/win_app.py` if new page |

## Procedure

1. From diff / parent notes: what **commands, steps, or selection rules** changed?
2. Update every matching guide surface (do not leave Telegram-only docs stale).
3. Keep Hebrew concise, command examples in `` `הכל` `` / `` `החלף X Y` `` style matching the bot.
4. Reflect current truths:
   - `הכל` = cash buys only (not swaps)
   - Method 2 = breakout, not blind open fill
   - Morning empty entry may send “אין קניות היום”
   - Intraday suggestions include copy-paste how-to
5. If a command was added: ensure it appears in `telegram_guide` commands section.
6. Optional: skim `#/guide` content for contradictions; no need to launch UI if code is clear.
7. Report files touched + bullet list of doc deltas.

## Do not

- Invent features not in code
- Commit unless asked
- Rewrite unrelated guide sections
