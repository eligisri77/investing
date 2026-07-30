"""Capital allocation options after partial plan approval."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from trading_pulse.telegram.telegram_format import SEP, escape_html, user_guide_done, user_guide_step2


def _approved_recs(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in plan.get("recommendations", []) if r.get("approved")]


def planned_per_trade_cap(plan: dict[str, Any]) -> float:
    if plan.get("planned_per_trade_cap"):
        return float(plan["planned_per_trade_cap"])
    recs = plan.get("recommendations") or []
    if recs:
        return float(recs[0].get("capital_usd", 0))
    return 0.0


def _current_holdings(state: dict[str, Any]) -> list[dict[str, Any]]:
    from trading_pulse.agent.positions import holdings_snapshot

    return holdings_snapshot(state)


def estimate_tomorrow_slots(cfg: Any, state: dict[str, Any], approved_new_count: int) -> int:
    current_holdings = len(_current_holdings(state))
    after_entry = current_holdings + approved_new_count
    slots_left = max(0, int(getattr(cfg, "max_open_positions", 4)) - after_entry)
    return min(slots_left, int(getattr(cfg, "max_trades_per_day", 3)))


def _max_per_position(cfg: Any, equity: float) -> float:
    return equity * float(getattr(cfg, "max_position_pct", 0.25))


def _round_amounts(amounts: list[float], target_total: float) -> list[float]:
    if not amounts:
        return []
    rounded = [round(a, 2) for a in amounts]
    diff = round(target_total - sum(rounded), 2)
    if rounded and abs(diff) >= 0.01:
        rounded[0] = round(rounded[0] + diff, 2)
    return rounded


def _rank_weights(n: int) -> list[float]:
    weights = [float(n - i) for i in range(n)]
    total = sum(weights) or 1.0
    return [w / total for w in weights]


def _portfolio_totals(
    equity: float,
    holdings: list[dict[str, Any]],
    new_amounts: list[float],
) -> dict[str, float]:
    held_total = round(sum(float(h.get("capital_usd", 0)) for h in holdings), 2)
    new_total = round(sum(new_amounts), 2)
    deployed = round(held_total + new_total, 2)
    cash = round(max(0.0, equity - deployed), 2)
    return {
        "held_total_usd": held_total,
        "new_total_usd": new_total,
        "deployed_total_usd": deployed,
        "cash_usd": cash,
    }


def _is_method2_rec(rec: dict[str, Any]) -> bool:
    return str(rec.get("strategy") or "") == "method2" or bool(rec.get("sleeve"))


def _sleeve_aware_equal_amounts(
    approved_new: list[dict[str, Any]],
    deployable: float,
) -> list[float]:
    """Keep שיטה 2 planned capital; split the rest equally across main picks."""
    if not approved_new:
        return []
    sleeve_idxs = [i for i, r in enumerate(approved_new) if _is_method2_rec(r)]
    main_idxs = [i for i, r in enumerate(approved_new) if not _is_method2_rec(r)]
    amounts = [0.0] * len(approved_new)
    sleeve_total = 0.0
    for i in sleeve_idxs:
        amt = float(approved_new[i].get("capital_usd") or 0)
        amounts[i] = amt
        sleeve_total += amt
    main_budget = max(0.0, float(deployable) - sleeve_total)
    if main_idxs:
        each = main_budget / len(main_idxs)
        for i in main_idxs:
            amounts[i] = each
    elif sleeve_idxs and sleeve_total <= 0:
        # Only sleeve picks with no capital — fall back to equal
        each = deployable / len(approved_new)
        return [each] * len(approved_new)
    return amounts


def compute_allocation_options(
    cfg: Any,
    plan: dict[str, Any],
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    approved = _approved_recs(plan)
    holdings = _current_holdings(state)
    held_syms = {str(h["symbol"]) for h in holdings}
    approved_new = [r for r in approved if str(r["symbol"]) not in held_syms]
    if not approved_new:
        return []

    equity = float(state.get("equity", plan.get("equity_snapshot", 0)))
    from trading_pulse.agent.positions import available_capital, deployed_capital

    held_total = deployed_capital(state)
    deployable = available_capital(cfg, state)
    if deployable <= 0 and held_total == 0:
        deployable = float(plan.get("available_capital_usd", equity))

    n = len(approved_new)
    max_pos = _max_per_position(cfg, equity)
    original_cap = planned_per_trade_cap(plan)
    tomorrow_slots = estimate_tomorrow_slots(cfg, state, n)

    equal_amounts = _sleeve_aware_equal_amounts(approved_new, deployable)

    original_amounts = []
    for r in approved_new:
        if _is_method2_rec(r):
            original_amounts.append(float(r.get("capital_usd") or 0))
        else:
            original_amounts.append(min(original_cap, max_pos))
    reserve_original = max(0.0, deployable - sum(original_amounts))

    rank_weights = _rank_weights(n)
    rank_amounts = [deployable * w for w in rank_weights]

    # Full deploy: max to #1, rest equal on remainder
    if n == 1:
        top_heavy_amounts = [deployable]
    else:
        first = min(max_pos, deployable)
        rest_each = max(0.0, deployable - first) / (n - 1)
        top_heavy_amounts = [first] + [rest_each] * (n - 1)

    # Partial deploy: only half of deployable, split equally
    half_deploy = deployable * 0.5
    half_each = half_deploy / n if n else 0.0
    half_amounts = [half_each] * n

    def pack(
        option_id: int,
        title: str,
        description: str,
        new_amounts: list[float],
        *,
        full_invest: bool,
        reserve_note: str = "",
    ) -> dict[str, Any]:
        symbols = [str(r["symbol"]) for r in approved_new]
        target = deployable if full_invest else min(sum(new_amounts), deployable)
        rounded = _round_amounts(new_amounts, target) if full_invest else _round_amounts(new_amounts, sum(new_amounts))
        totals = _portfolio_totals(equity, holdings, rounded)
        return {
            "id": option_id,
            "title": title,
            "description": description,
            "full_invest": full_invest,
            "symbols": symbols,
            "amounts": rounded,
            "holdings": [
                {
                    "symbol": str(h["symbol"]),
                    "capital_usd": round(float(h.get("capital_usd", 0)), 2),
                    "days_held": int(h.get("days_held", 0)),
                }
                for h in holdings
            ],
            "new_entries": [
                {"symbol": sym, "capital_usd": amt}
                for sym, amt in zip(symbols, rounded, strict=False)
            ],
            "new_total_usd": totals["new_total_usd"],
            "held_total_usd": totals["held_total_usd"],
            "total_usd": totals["new_total_usd"],
            "deployed_total_usd": totals["deployed_total_usd"],
            "reserve_usd": totals["cash_usd"],
            "reserve_note": reserve_note,
            "equity_usd": round(equity, 2),
        }

    full_options = [
        pack(
            1,
            "שווה — השקעה מלאה",
            (
                f"שרוול נרות סיניים 2 נשמר; יתרת הפנוי (${deployable:.0f}) מתחלקת שווה בין שאר הכניסות."
                if any(_is_method2_rec(r) for r in approved_new)
                else f"כל ההון הפנוי (${deployable:.0f}) מתחלק שווה בין הכניסות החדשות."
            ),
            equal_amounts,
            full_invest=True,
            reserve_note="כל הפנוי מנוצל",
        ),
        pack(
            2,
            "דירוג — השקעה מלאה",
            "כל הפנוי — יותר ל-#1, פחות ל-#2 וכו' לפי סדר ההמלצה.",
            rank_amounts,
            full_invest=True,
            reserve_note="כל הפנוי מנוצל",
        ),
        pack(
            3,
            "מקס לראשונה — השקעה מלאה",
            f"#1 מקבל עד {int(getattr(cfg, 'max_position_pct', 0.25) * 100)}% מההון, השאר שווה על הנותר.",
            top_heavy_amounts,
            full_invest=True,
            reserve_note="כל הפנוי מנוצל",
        ),
    ]
    partial_options = [
        pack(
            4,
            "לפי התוכנית + מזומן למחר",
            f"סכום מקורי ${original_cap:.0f} לכל כניסה — שומר מזומן להמלצות הבאות.",
            original_amounts,
            full_invest=False,
            reserve_note=(
                f"מזומן למחר: ~${reserve_original:.0f} · עד {tomorrow_slots} כניסות חדשות"
                if tomorrow_slots
                else f"מזומן נשאר: ~${reserve_original:.0f}"
            ),
        ),
        pack(
            5,
            "שמרני — חצי פנוי",
            f"רק 50% מהפנוי (${half_deploy:.0f}) מתחלק שווה — השאר נשאר במזומן.",
            half_amounts,
            full_invest=False,
            reserve_note=f"מזומן נשאר: ~${max(0.0, deployable - half_deploy):.0f}",
        ),
    ]
    return full_options + partial_options


def _entries_inline(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "—"
    return " · ".join(
        f"{escape_html(e['symbol'])} ${float(e['capital_usd']):.0f}" for e in entries
    )


def format_allocation_option_summary(option: dict[str, Any]) -> list[str]:
    """Compact one-glance lines for a single allocation option."""
    lines: list[str] = []
    holdings = option.get("holdings") or []
    new_entries = option.get("new_entries") or []

    if holdings:
        lines.append(f"  📂 מחזיקים: {_entries_inline(holdings)}")
    if new_entries:
        lines.append(f"  🆕 חדש: {_entries_inline(new_entries)}")

    deployed = float(option.get("deployed_total_usd", 0))
    cash = float(option.get("reserve_usd", 0))
    if option.get("full_invest"):
        lines.append(f"  💰 סה\"כ מושקע <b>${deployed:.0f}</b> · מזומן <b>$0</b>")
    else:
        lines.append(f"  💰 סה\"כ מושקע <b>${deployed:.0f}</b> · מזומן נשאר <b>${cash:.0f}</b>")
    return lines


def format_allocation_lines(option: dict[str, Any]) -> list[str]:
    return format_allocation_option_summary(option)


def format_allocation_prompt(
    plan: dict[str, Any],
    options: list[dict[str, Any]],
    *,
    trading_day: str,
    state: dict[str, Any] | None = None,
) -> str:
    approved = _approved_recs(plan)
    holdings = _current_holdings(state or {})
    held_syms = {str(h["symbol"]) for h in holdings}
    new_syms = [str(r["symbol"]) for r in approved if str(r["symbol"]) not in held_syms]
    syms = ", ".join(new_syms)
    equity = float(options[0].get("equity_usd", plan.get("equity_snapshot", 0))) if options else float(
        plan.get("equity_snapshot", 0)
    )
    held_total = round(sum(float(h.get("capital_usd", 0)) for h in holdings), 2)
    deployable = round(max(0.0, equity - held_total), 2)

    lines = [
        "<b>💵 שלב 2 — חלוקת הון</b>",
        f"<b>יום מסחר:</b> {escape_html(trading_day)}",
        "",
        f"<b>מאושרות:</b> {escape_html(syms)}",
        f"הון <b>${equity:.0f}</b> · פנוי לחלוקה <b>${deployable:.0f}</b>",
        "",
        user_guide_step2(),
        "",
    ]
    if holdings:
        held_list = ", ".join(str(h["symbol"]) for h in holdings)
        lines.append(f"📂 מחזיקים (ללא שינוי): <b>{escape_html(held_list)}</b>")
        lines.append("")

    full_opts = [o for o in options if o.get("full_invest")]
    partial_opts = [o for o in options if not o.get("full_invest")]

    lines.append("<b>🔵 השקעה מלאה</b> — כל הפנוי מנוצל")
    lines.append("")
    for opt in full_opts:
        lines.append(f"<b>ח{opt['id']} — {escape_html(opt['title'])}</b>")
        lines.append(f"<i>{escape_html(opt['description'])}</i>")
        lines.extend(format_allocation_option_summary(opt))
        lines.append("")

    if partial_opts:
        lines.append("<b>🟡 עם מזומן</b> — חלק נשאר לימים הבאים")
        lines.append("")
        for opt in partial_opts:
            lines.append(f"<b>ח{opt['id']} — {escape_html(opt['title'])}</b>")
            lines.append(f"<i>{escape_html(opt['description'])}</i>")
            lines.extend(format_allocation_option_summary(opt))
            if opt.get("reserve_note"):
                lines.append(f"  <i>{escape_html(str(opt['reserve_note']))}</i>")
            lines.append("")

    cmds = " · ".join(f"<code>ח{i}</code>" for i in range(1, len(options) + 1))
    lines.append(f"<b>👉 בחר אחת:</b> {cmds}")
    return "\n".join(lines).strip()


def apply_allocation_option(plan: dict[str, Any], option_id: int, options: list[dict[str, Any]]) -> dict[str, Any] | None:
    chosen = next((o for o in options if o["id"] == option_id), None)
    if chosen is None:
        return None

    approved = _approved_recs(plan)
    approved_new = [r for r in approved if str(r["symbol"]) not in {str(h["symbol"]) for h in (chosen.get("holdings") or [])}]
    symbol_to_amount = dict(zip(chosen["symbols"], chosen["amounts"], strict=False))
    for rec in approved_new:
        sym = str(rec["symbol"])
        if sym in symbol_to_amount:
            rec["capital_usd"] = round(float(symbol_to_amount[sym]), 2)

    plan["allocation"] = {
        "status": "applied",
        "selected_option": option_id,
        "title": chosen["title"],
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "new_total_usd": chosen.get("new_total_usd", chosen.get("total_usd", 0)),
        "held_total_usd": chosen.get("held_total_usd", 0),
        "deployed_total_usd": chosen.get("deployed_total_usd", 0),
        "reserve_usd": chosen.get("reserve_usd", 0),
        "holdings": chosen.get("holdings", []),
        "amounts": {sym: amt for sym, amt in zip(chosen["symbols"], chosen["amounts"], strict=False)},
    }
    return chosen


def format_allocation_applied(chosen: dict[str, Any], trading_day: str) -> str:
    opt_id = chosen.get("id", "?")
    lines = [
        f"<b>✅ חלוקה נשמרה</b> · ח{opt_id}",
        f"<b>יום מסחר:</b> {escape_html(trading_day)}",
        f"<b>אופציה:</b> {escape_html(chosen.get('title', ''))}",
        "",
        "<b>סכומים לכניסה מחר:</b>",
    ]
    for entry in chosen.get("new_entries") or []:
        lines.append(
            f"• <b>{escape_html(entry['symbol'])}</b> "
            f"<b>${float(entry['capital_usd']):.0f}</b>"
        )
    cash = float(chosen.get("reserve_usd", 0))
    if cash > 0.01:
        lines.append(f"\n💵 מזומן נשאר: <b>${cash:.0f}</b>")
    else:
        lines.append("\n✅ כל ההון הפנוי מושקע")
    lines.extend(["", SEP, user_guide_done()])
    return "\n".join(lines)


def allocation_pending(plan: dict[str, Any]) -> bool:
    alloc = plan.get("allocation") or {}
    if alloc.get("status") == "applied":
        return False
    if alloc.get("manual_offer_flow"):
        # The sequential Telegram offer queue (offer_queue.py) also parks
        # allocation.status at "pending" between individual offer replies,
        # but it never populates `options` and resolves itself once the
        # queue is exhausted — it must not surface the old ח1..ח5
        # multi-option allocation-choice UI (Telegram fallback text or the
        # #/plan dashboard card) while a conversation is still in progress.
        return False
    return bool(_approved_recs(plan))


def allocation_options_payload(cfg: Any, plan: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    """Dashboard-friendly allocation options (read-only)."""
    options = compute_allocation_options(cfg, plan, state)
    rows: list[dict[str, Any]] = []
    for opt in options:
        amounts = {
            sym: round(float(amt), 2)
            for sym, amt in zip(opt.get("symbols", []), opt.get("amounts", []), strict=False)
        }
        rows.append(
            {
                "id": opt["id"],
                "title": opt.get("title", ""),
                "description": opt.get("description", ""),
                "full_invest": bool(opt.get("full_invest")),
                "summary_lines": format_allocation_option_summary(opt),
                "amounts": amounts,
                "deployed_total_usd": opt.get("deployed_total_usd", opt.get("new_total_usd", 0)),
                "reserve_usd": opt.get("reserve_usd", 0),
            }
        )
    return rows


def ensure_allocation_options(cfg: Any, plan: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    options = compute_allocation_options(cfg, plan, state)
    plan.setdefault("allocation", {})["options"] = options
    return options
