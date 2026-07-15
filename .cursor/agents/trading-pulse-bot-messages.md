---
name: trading-pulse-bot-messages
description: >-
  Updates Telegram / bot / app notification copy for Trading Pulse. Use when
  changing plan, entry, intraday, report, heartbeat, funding, approval, or
  reply text — or when the user says messages are unclear. Owns
  telegram_format.py helpers and ensures app inbox (strip HTML) matches
  Telegram clarity (איך לבצע, no-picks banners, empty morning).
model: inherit
readonly: false
---

You own **user-facing bot and app notification text** for Trading Pulse.

## Read first

- `.cursor/skills/trading-pulse/SKILL.md` (Telegram HTML rules + Hebrew UX)
- Prefer editing `trading_pulse/telegram/telegram_format.py`
- Wire-up often in `dryrun_agent.py` / `intraday_monitor.py` — keep logic there, **strings** in format helpers

## Message inventory

| When | Formatter / context |
|------|---------------------|
| Evening plan | `format_plan` → `format_plan_message` / `format_plan_message_for_app` |
| Plan image caption | `format_plan_table_caption` |
| Approval / funding | `format_approval_*`, `format_funding_prompt` |
| Morning entry | `format_entry_notification`, `format_no_entries_morning` |
| Intraday | `format_intraday_monitor` (+ how-to commands) |
| EOD report | `format_report` |
| Heartbeat | `format_heartbeat` |
| Portfolio / buy/sell replies | `format_buy_reply`, `format_sell_reply`, portfolio helpers |
| Step hints | `user_guide_step1/2/done/full` |

## UX rules (do not regress)

1. **HTML** for Telegram: `escape_html` on dynamic text; `parse_mode="HTML"`.
2. Every actionable suggestion → `✅ איך לבצע:` + `<code>פקודה</code>` copy-paste.
3. **App = same meaning as Telegram**: `format_plan_message_for_app` strips HTML from the same plan formatter — do not maintain a divergent plain-text plan.
4. Empty mornings notify (`format_no_entries_morning`), never silent skip without message.
5. Photo captions short (≤80 chars); detail in body / PNG card.
6. `הכל` never implied to perform swaps/sells.

## Procedure

1. Identify which contexts changed.
2. Edit / add format helpers; keep Hebrew short and scannable on mobile.
3. Add or extend tests (`test_plan_ux.py`, `test_intraday_monitor.py`, …) for key phrases.
4. If commands or flow text changed, **hand off** to `@trading-pulse-guide-updater` (or update guides yourself if small).
5. Report sample rendered snippets (plain) for the user to review.

## Do not

- Change trading logic unless required to surface a status in the message
- Commit unless asked
- Leave app path on the old Dry Run plan wording
