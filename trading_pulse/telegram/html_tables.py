"""Hebrew HTML tables rendered to PNG for Telegram (RTL-safe numbers).

Canonical signed formats (leading sign):
  -3.5%   -$4.00   +$1.67
Every number sits under a Hebrew column header or in a labeled key/value row.
"""

from __future__ import annotations

import html
import logging
from typing import Any

from trading_pulse.telegram.html_render import try_render_html_to_png

# Theme (matches dashboard / reply cards)
# Large type: Telegram shrinks tall images — crop + big fonts keep text readable on phone.
_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  background: #0a0a18;
  color: #e6ebf5;
  font-family: "Segoe UI", Arial, "David", sans-serif;
  padding: 14px 12px 16px;
  direction: rtl;
  width: 100%;
}
.card {
  background: #121224;
  border: 2px solid #282846;
  border-radius: 16px;
  padding: 22px 18px 24px;
  max-width: 100%;
  display: inline-block;
  min-width: calc(100% - 4px);
}
h1 {
  color: #e6ebf5;
  font-size: 32px;
  font-weight: 700;
  margin-bottom: 10px;
  border-right: 5px solid #00f0ff;
  padding-right: 12px;
  line-height: 1.25;
}
h1.green { border-right-color: #00ff88; }
h1.pink { border-right-color: #ff2d95; }
.sub {
  color: #8c91a5;
  font-size: 18px;
  margin: 0 14px 16px 0;
  line-height: 1.45;
}
h2 {
  color: #00f0ff;
  font-size: 22px;
  margin: 20px 0 10px;
  font-weight: 700;
}
table.data {
  width: 100%;
  border-collapse: collapse;
  font-size: 18px;
  margin-bottom: 6px;
}
table.data th {
  background: #181830;
  color: #ff2d95;
  font-weight: 700;
  text-align: right;
  padding: 12px 8px;
  border-bottom: 1px solid #282846;
  white-space: nowrap;
  font-size: 17px;
}
table.data td {
  padding: 12px 8px;
  border-bottom: 1px solid #1c1c30;
  text-align: right;
  vertical-align: middle;
  font-size: 18px;
}
table.data tr:nth-child(even) td { background: #0e0e1e; }
td.num, th.num {
  direction: ltr;
  unicode-bidi: isolate;
  text-align: left;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  white-space: nowrap;
  font-size: 19px;
}
td.sym {
  direction: ltr;
  unicode-bidi: isolate;
  font-weight: 700;
  color: #00f0ff;
  text-align: left;
  font-size: 20px;
}
td.pos, .pos { color: #00ff88 !important; }
td.neg, .neg { color: #ff3366 !important; }
td.muted, .muted { color: #8c91a5; }
table.kv {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0 8px;
  font-size: 20px;
}
table.kv td {
  background: #0c0c1a;
  border: 1px solid #282846;
  padding: 14px 12px;
}
table.kv td.k {
  width: 48%;
  color: #8c91a5;
  font-size: 17px;
  border-radius: 0 10px 10px 0;
  border-left: none;
}
table.kv td.v {
  border-radius: 10px 0 0 10px;
  border-right: none;
  font-weight: 700;
  direction: ltr;
  unicode-bidi: isolate;
  text-align: left;
  font-size: 22px;
}
.chips { margin-top: 14px; }
.chip {
  display: inline-block;
  background: #280c1c;
  border: 1px solid #5a1937;
  color: #ff2d95;
  padding: 8px 14px;
  border-radius: 10px;
  margin: 0 0 8px 8px;
  font-size: 18px;
  font-weight: 700;
  direction: rtl;
}
.foot {
  color: #8c91a5;
  font-size: 16px;
  margin-top: 14px;
  line-height: 1.4;
}
.alert {
  background: #0c0c1a;
  border: 1px solid #282846;
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 8px;
  font-size: 17px;
  line-height: 1.4;
}
.alert.sev3 { border-color: #ff3366; color: #ff3366; }
.alert.sev2 { border-color: #ff2d95; color: #ff9ec8; }
"""


def fmt_pct(value: float | None, *, digits: int = 1) -> str:
    """Signed percent with leading sign: -3.5% / +3.5% / 0.0%"""
    if value is None:
        return "—"
    v = float(value)
    body = f"{abs(v):.{digits}f}%"
    if v < 0:
        return f"-{body}"
    if v > 0:
        return f"+{body}"
    return body


def fmt_money_plain(value: float | None, *, digits: int = 2, whole: bool = False) -> str:
    """Unsigned money for labels like מושקע / מחיר."""
    if value is None:
        return "—"
    v = float(value)
    if whole:
        return f"${v:.0f}"
    return f"${v:.{digits}f}"


def fmt_money(
    value: float | None,
    *,
    signed: bool = False,
    digits: int = 2,
    whole: bool = False,
) -> str:
    """Money with optional leading sign: -$4.00 / +$4.00 / $4.00"""
    if value is None:
        return "—"
    if not signed:
        return fmt_money_plain(value, digits=digits, whole=whole)
    v = float(value)
    body = f"${abs(v):.0f}" if whole else f"${abs(v):.{digits}f}"
    if v < 0:
        return f"-{body}"
    if v > 0:
        return f"+{body}"
    return body


def _pnl_class(value: float) -> str:
    if value > 0:
        return "pos"
    if value < 0:
        return "neg"
    return ""


def _esc(text: Any) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def strategy_col(obj: dict[str, Any] | None) -> str:
    """Short method label for a narrow table column."""
    from trading_pulse.agent.strategy_labels import strategy_label

    label = strategy_label(obj) or ""
    # Compact for table width
    replacements = (
        ("נרות סיניים 2", "נרות 2"),
        ("מומנטום וציון", "מומנטום"),
        ("תיקון במגמה · ניסיוני", "תיקון"),
        ("VCP · התכווצות ופריצה · ניסיוני", "VCP"),
        ("חוזק יחסי · ניסיוני", "חוזק יחסי"),
        ("נרות Rising Three", "Rising Three"),
    )
    for a, b in replacements:
        label = label.replace(a, b)
    if label:
        return label
    # Older positions may lack strategy_id — still show a clear Hebrew tag.
    return "לא תויגה"


def wrap_card_html(
    title: str,
    body_html: str,
    *,
    subtitle: str = "",
    accent: str = "cyan",
    footer: str = "",
) -> str:
    accent_cls = {"green": "green", "pink": "pink"}.get(accent, "")
    sub = f'<p class="sub">{_esc(subtitle)}</p>' if subtitle else ""
    foot = f'<p class="foot">{_esc(footer)}</p>' if footer else ""
    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head><meta charset="utf-8"><style>{_CSS}</style></head>
<body>
<div class="card">
  <h1 class="{accent_cls}">{_esc(title)}</h1>
  {sub}
  {body_html}
  {foot}
</div>
</body>
</html>"""


def render_table_png(
    html_doc: str,
    *,
    width: int = 720,
    height: int = 2400,
    pil_fallback: bytes | None = None,
) -> bytes:
    """Screenshot HTML; optional PIL bytes if browser unavailable."""
    png = try_render_html_to_png(html_doc, width=width, height=height)
    if png:
        return png
    if pil_fallback is not None:
        logging.warning("HTML table render failed; using PIL fallback")
        return pil_fallback
    raise RuntimeError("HTML table render failed and no PIL fallback")


def _table(headers: list[str], rows: list[list[tuple[str, str]]], *, numeric_cols: set[int] | None = None) -> str:
    """rows: list of (text, css_class) cells."""
    numeric_cols = numeric_cols or set()
    ths = []
    for i, h in enumerate(headers):
        cls = "num" if i in numeric_cols else ""
        ths.append(f'<th class="{cls}">{_esc(h)}</th>')
    body_rows = []
    for row in rows:
        tds = []
        for i, (text, cls) in enumerate(row):
            base = "num" if i in numeric_cols else ""
            classes = " ".join(c for c in (base, cls) if c)
            tds.append(f'<td class="{classes}">{_esc(text)}</td>')
        body_rows.append("<tr>" + "".join(tds) + "</tr>")
    if not body_rows:
        span = len(headers)
        body_rows.append(f'<tr><td colspan="{span}" class="muted">—</td></tr>')
    return (
        '<table class="data"><thead><tr>'
        + "".join(ths)
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table>"
    )


def _kv_table(rows: list[tuple[str, str, str]]) -> str:
    """rows: (label, value, css_class)."""
    parts = []
    for label, value, cls in rows:
        parts.append(
            "<tr>"
            f'<td class="k">{_esc(label)}</td>'
            f'<td class="v {cls}">{_esc(value)}</td>'
            "</tr>"
        )
    return '<table class="kv">' + "".join(parts) + "</table>"


# ---------------------------------------------------------------------------
# Dense message builders
# ---------------------------------------------------------------------------


def html_intraday(report: Any) -> str:
    from trading_pulse.telegram.telegram_format import _intraday_howto_command

    holdings = list(getattr(report, "holdings", None) or [])[:8]
    floor_sells = list(getattr(report, "floor_sells", None) or [])[:6]
    alerts = list(getattr(report, "alerts", None) or [])[:6]
    suggestions = list(getattr(report, "suggestions", None) or [])[:4]

    parts: list[str] = []

    if holdings:
        parts.append("<h2>מושקע עכשיו</h2>")
        rows = []
        for i, h in enumerate(holdings):
            cap = float(h.get("capital_usd") or 0)
            last = float(h.get("last") or 0)
            floor = h.get("floor_price")
            pnl_pct = float(h.get("pnl_pct") or 0)
            day_pct = float(h.get("day_change_pct") or 0)
            pnl_usd = cap * pnl_pct / 100.0 if cap else 0.0
            marked = cap + pnl_usd
            rows.append(
                [
                    (str(i + 1), ""),
                    (str(h.get("symbol") or "?"), "sym"),
                    (strategy_col(h), "muted"),
                    (fmt_money_plain(cap, whole=True), ""),
                    (fmt_money_plain(last), ""),
                    (fmt_money_plain(float(floor), digits=2) if floor else "—", ""),
                    (fmt_money_plain(marked, whole=True), ""),
                    (fmt_pct(pnl_pct), _pnl_class(pnl_pct)),
                    (fmt_pct(day_pct), _pnl_class(day_pct)),
                    (fmt_money(pnl_usd, signed=True, whole=True), _pnl_class(pnl_usd)),
                ]
            )
        parts.append(
            _table(
                [
                    "#",
                    "סימול",
                    "שיטה",
                    "מושקע",
                    "מחיר",
                    "רף יציאה",
                    "שווי",
                    "מהכניסה",
                    "היום",
                    "רווח",
                ],
                rows,
                numeric_cols={0, 3, 4, 5, 6, 7, 8, 9},
            )
        )

    if floor_sells:
        parts.append("<h2>נמכר — מחיר תחתון</h2>")
        rows = []
        for t in floor_sells:
            pnl = float(t.get("pnl_usd") or 0)
            rows.append(
                [
                    (str(t.get("symbol") or "?"), "sym"),
                    (fmt_money_plain(float(t.get("exit_price") or 0)), ""),
                    (fmt_money_plain(float(t.get("floor_price") or 0)), ""),
                    ("רווח" if pnl >= 0 else "הפסד", _pnl_class(pnl)),
                    (fmt_money(pnl, signed=True), _pnl_class(pnl)),
                ]
            )
        parts.append(
            _table(
                ["סימול", "מחיר יציאה", "רף", "תוצאה", "סכום"],
                rows,
                numeric_cols={1, 2, 4},
            )
        )

    if alerts:
        parts.append("<h2>חריגות</h2>")
        for alert in sorted(alerts, key=lambda a: -getattr(a, "severity", 0)):
            sev = int(getattr(alert, "severity", 0) or 0)
            cls = "sev3" if sev >= 3 else "sev2" if sev >= 2 else ""
            sym = _esc(getattr(alert, "symbol", "") or "")
            msg = _esc(getattr(alert, "message", "") or "")
            parts.append(f'<div class="alert {cls}"><b class="sym">{sym}</b> — {msg}</div>')

    if suggestions:
        parts.append("<h2>הצעות</h2>")
        for sug in suggestions:
            kind = getattr(sug, "kind", "")
            sym = str(getattr(sug, "symbol", "") or "")
            msg = str(getattr(sug, "message", "") or "")
            if kind == "buy":
                head = f"רכישה {sym}"
            elif kind == "swap":
                head = "החלפה"
            elif kind == "sell":
                head = f"מכירה {sym}"
            else:
                head = f"מעקב {sym}"
            parts.append(f'<div class="alert">{_esc(head)} — {_esc(msg)}</div>')

    chips = []
    for sug in suggestions:
        cmd = _intraday_howto_command(sug)
        if cmd and cmd not in chips:
            chips.append(cmd)
    if chips:
        parts.append('<h2>איך לבצע</h2><div class="chips">')
        for c in chips:
            parts.append(f'<span class="chip">{_esc(c)}</span>')
        parts.append("</div>")
        footer = "הצעה בלבד — לא ביצוע אוטומטי"
    elif floor_sells and not suggestions:
        footer = "יציאה אוטומטית בוצעה — אין פעולה נוספת"
    else:
        footer = "למעקב בלבד — אין פעולה נדרשת"

    return wrap_card_html("מעקב שעתי — מסחר פעיל", "".join(parts), footer=footer)


def html_daily_report(report: dict[str, Any]) -> str:
    day = str(report.get("trading_day") or "")
    pnl = float(report.get("pnl_usd") or 0)
    unrealized = float(report.get("unrealized_pnl_usd") or 0)
    equity_before = float(report.get("equity_before") or 0)
    equity_after = float(report.get("equity_after") or 0)
    marked = report.get("equity_marked_usd")
    fees = float(report.get("fees_usd") or 0)
    monthly = str(report.get("monthly_target_summary") or "").strip()
    held = list(report.get("held_eod") or [])[:10]
    executed = list(report.get("executed") or [])
    manual = [t for t in executed if t.get("manual_exit") or t.get("exit_reason") == "user_sell"][:8]
    automatic = [t for t in executed if t not in manual][:8]

    exit_he = {
        "stop_loss": "סטופ",
        "floor_price": "מחיר תחתון",
        "take_profit": "יעד",
        "close": "סגירה",
        "max_hold_days": "מקס ימים",
        "user_sell": "מכירה ידנית",
    }

    kv = [
        ("הון בתחילת היום", fmt_money_plain(equity_before), ""),
        ("שינוי ממומש היום", fmt_money(pnl, signed=True), _pnl_class(pnl)),
        ("הון בסוף היום", fmt_money_plain(equity_after), ""),
    ]
    if fees:
        kv.append(("עמלות", fmt_money_plain(fees), "muted"))
    if unrealized or held:
        kv.append(("רווח עתידי (לא ממומש)", fmt_money(unrealized, signed=True), _pnl_class(unrealized)))
    if marked is not None:
        kv.append(("שווי משוער כולל", fmt_money_plain(float(marked)), ""))

    parts = [_kv_table(kv)]
    if monthly:
        parts.append(f'<p class="sub">{_esc(monthly)}</p>')

    if held:
        parts.append("<h2>מחזיקים בסוף היום</h2>")
        rows = []
        for i, pos in enumerate(held):
            ur = float(pos.get("unrealized_pnl_usd") or 0)
            ur_pct = pos.get("unrealized_pnl_pct")
            rows.append(
                [
                    (str(i + 1), ""),
                    (str(pos.get("symbol") or "?"), "sym"),
                    (strategy_col(pos), "muted"),
                    (fmt_money_plain(float(pos.get("capital_usd") or 0), whole=True), ""),
                    (str(pos.get("days_held", "—")), ""),
                    (fmt_money(ur, signed=True), _pnl_class(ur)),
                    (fmt_pct(float(ur_pct) if ur_pct is not None else None), _pnl_class(float(ur_pct or 0))),
                ]
            )
        parts.append(
            _table(
                ["#", "סימול", "שיטה", "מושקע", "ימים", "רווח פתוח", "מהכניסה"],
                rows,
                numeric_cols={0, 3, 4, 5, 6},
            )
        )

    def _closed_section(title: str, trades: list[dict[str, Any]]) -> None:
        if not trades:
            return
        parts.append(f"<h2>{_esc(title)}</h2>")
        rows = []
        for t in trades:
            p = float(t.get("pnl_usd") or 0)
            pct = float(t.get("pnl_pct") or 0)
            reason = exit_he.get(str(t.get("exit_reason") or ""), str(t.get("exit_reason") or "—"))
            rows.append(
                [
                    (str(t.get("symbol") or "?"), "sym"),
                    (strategy_col(t), "muted"),
                    (reason, ""),
                    (str(t.get("days_held", "—")), ""),
                    (fmt_money(p, signed=True), _pnl_class(p)),
                    (fmt_pct(pct), _pnl_class(pct)),
                ]
            )
        parts.append(
            _table(
                ["סימול", "שיטה", "סיבת יציאה", "ימים", "רווח", "אחוז"],
                rows,
                numeric_cols={3, 4, 5},
            )
        )

    _closed_section("נסגרו — מכירה ידנית", manual)
    _closed_section("נסגרו — אוטומטי", automatic)

    if not held and not executed:
        parts.append('<p class="foot">אין פעילות היום</p>')

    return wrap_card_html(f"דוח יומי · {day}", "".join(parts))


def html_portfolio(data: dict[str, Any]) -> str:
    from trading_pulse.agent.portfolio_index import attach_slots_to_portfolio
    from trading_pulse.core.schedule_tz import format_local_entry_moment

    data = attach_slots_to_portfolio(data)
    equity = float(data.get("equity", 0))
    marked = float(data.get("open_marked_usd", data.get("open_capital_usd", 0)))
    unrealized = float(data.get("unrealized_pnl_usd", 0))
    realized = float(data.get("total_realized_pnl", 0))
    positions = data.get("open_positions") or []
    holding = [p for p in positions if p.get("status") == "holding"]
    pending = [p for p in positions if p.get("status") == "pending_market_entry"]
    holding_cap = sum(float(p.get("capital_usd", 0)) for p in holding)
    cash = float(data.get("cash_usd", max(0.0, equity - holding_cap)))

    parts = [
        _kv_table(
            [
                ("הון", fmt_money_plain(equity), ""),
                ("מזומן פנוי", fmt_money_plain(cash, whole=True), ""),
                ("שווי פתוח", fmt_money_plain(marked, whole=True), ""),
                ("רווח פתוח", fmt_money(unrealized, signed=True, whole=True), _pnl_class(unrealized)),
                ("רווח ממומש", fmt_money(realized, signed=True), _pnl_class(realized)),
            ]
        )
    ]

    if pending:
        parts.append("<h2>מאושר — ממתין לפתיחה</h2>")
        rows = []
        for p in pending:
            rows.append(
                [
                    (str(p.get("symbol") or "?"), "sym"),
                    (strategy_col(p), "muted"),
                    (fmt_money_plain(float(p.get("capital_usd") or 0), whole=True), ""),
                    (str(p.get("scheduled_entry") or "פתיחת השוק"), ""),
                ]
            )
        parts.append(
            _table(["סימול", "שיטה", "סכום", "כניסה"], rows, numeric_cols={2})
        )

    if holding:
        parts.append("<h2>בתיק עכשיו</h2>")
        rows = []
        for i, p in enumerate(holding):
            try:
                slot_n = int(p.get("slot", i + 1))
            except (TypeError, ValueError):
                slot_n = i + 1
            ur = float(p.get("unrealized_pnl_usd") or 0)
            cap = float(p.get("capital_usd") or 0)
            ep = float(p.get("entry_price") or 0)
            mv = float(p.get("marked_value_usd", cap))
            rows.append(
                [
                    (str(slot_n), ""),
                    (str(p.get("symbol") or "?"), "sym"),
                    (strategy_col(p), "muted"),
                    (fmt_money_plain(cap, whole=True), ""),
                    (fmt_money_plain(ep), ""),
                    (fmt_money_plain(mv, whole=True), ""),
                    (fmt_money(ur, signed=True, whole=True), _pnl_class(ur)),
                    (format_local_entry_moment(p.get("entry_at")), "muted"),
                ]
            )
        parts.append(
            _table(
                ["#", "סימול", "שיטה", "מושקע", "מחיר כניסה", "שווי", "רווח פתוח", "כניסה"],
                rows,
                numeric_cols={0, 3, 4, 5, 6},
            )
        )
    elif not pending:
        parts.append('<p class="foot">אין פוזיציות פתוחות</p>')

    chips = ["מכור 1 $100", "מכור 1 200$ קנה 2 100$", "תקנה 1 $20"]
    parts.append("<h2>דוגמאות לפעולות בתיק</h2>")
    parts.append('<div class="chips">')
    for c in chips:
        parts.append(f'<span class="chip">{_esc(c)}</span>')
    parts.append("</div>")
    return wrap_card_html(
        "תיק השקעות",
        "".join(parts),
        footer="מספרים (#) לפי סדר בתיק · הצ׳יפים למטה הם דוגמאות בלבד",
    )


def html_allocation(
    plan: dict[str, Any],
    options: list[dict[str, Any]],
    *,
    trading_day: str,
) -> str:
    options = list(options or [])[:5]
    if not options:
        return wrap_card_html("שלב 2 — חלוקת הון", '<p class="foot">אין אופציות חלוקה</p>', accent="pink")

    equity = float(options[0].get("equity_usd", plan.get("equity_snapshot", 0)))
    holdings0 = options[0].get("holdings") or []
    held_total = round(sum(float(h.get("capital_usd", 0)) for h in holdings0), 2)
    deployable = round(max(0.0, equity - held_total), 2)
    new_syms = [str(e.get("symbol")) for e in (options[0].get("new_entries") or [])]

    parts = [
        _kv_table(
            [
                ("יום מסחר", trading_day, ""),
                ("מאושרות לכניסה", " · ".join(new_syms) if new_syms else "—", ""),
                ("הון", fmt_money_plain(equity, whole=True), ""),
                ("פנוי לחלוקה", fmt_money_plain(deployable, whole=True), ""),
            ]
        )
    ]

    rows = []
    for opt in options:
        oid = f"ח{opt.get('id')}"
        for e in opt.get("holdings") or []:
            rows.append(
                [
                    (oid, ""),
                    (str(opt.get("title") or ""), "muted"),
                    ("מחזיק", ""),
                    (str(e.get("symbol") or "?"), "sym"),
                    (fmt_money_plain(float(e.get("capital_usd") or 0), whole=True), ""),
                ]
            )
        for e in opt.get("new_entries") or []:
            rows.append(
                [
                    (oid, ""),
                    (str(opt.get("title") or ""), "muted"),
                    ("חדש", "pos"),
                    (str(e.get("symbol") or "?"), "sym"),
                    (fmt_money_plain(float(e.get("capital_usd") or 0), whole=True), ""),
                ]
            )
        deployed = float(opt.get("deployed_total_usd") or 0)
        cash = float(opt.get("reserve_usd") or 0)
        rows.append(
            [
                (oid, ""),
                (str(opt.get("title") or ""), "muted"),
                ("סיכום", "muted"),
                ("מושקע / מזומן", "muted"),
                (
                    f"{fmt_money_plain(deployed, whole=True)} / "
                    f"{'$0' if opt.get('full_invest') else fmt_money_plain(cash, whole=True)}",
                    "",
                ),
            ]
        )

    parts.append("<h2>השוואת אופציות</h2>")
    parts.append(
        _table(
            ["אופציה", "שם", "סוג", "סימול", "סכום"],
            rows,
            numeric_cols={4},
        )
    )
    chips = [f"ח{o['id']}" for o in options]
    parts.append('<h2>בחר אחת</h2><div class="chips">')
    for c in chips:
        parts.append(f'<span class="chip">{_esc(c)}</span>')
    parts.append("</div>")
    return wrap_card_html(
        "שלב 2 — חלוקת הון",
        "".join(parts),
        accent="pink",
        footer="שלח ח1…ח5 לבחירה",
    )


def html_entry(
    entries: list[dict[str, Any]],
    *,
    trading_day: str,
    subtitle: str | None = None,
) -> str:
    entries = list(entries or [])[:10]
    title = subtitle or "קנית"
    rows = []
    for i, e in enumerate(entries):
        side = str(e.get("side") or "LONG").upper()
        sym = str(e.get("symbol") or "?")
        if side == "SHORT":
            sym = f"{sym} שורט"
        rows.append(
            [
                (str(i + 1), ""),
                (sym, "sym"),
                (strategy_col(e), "muted"),
                (fmt_money_plain(float(e.get("capital_usd") or 0), whole=True), ""),
                (fmt_money_plain(float(e.get("entry_price") or 0)), ""),
            ]
        )
    body = _table(
        ["#", "סימול", "שיטת כניסה", "סכום", "מחיר כניסה"],
        rows,
        numeric_cols={0, 3, 4},
    )
    return wrap_card_html(
        f"{title} · {trading_day}",
        body,
        accent="green",
        footer="דוח סוף יום אחרי סגירת וול סטריט",
    )


def html_heartbeat(
    cfg: Any,
    state: dict[str, Any],
    *,
    market_day: bool = True,
    next_trading_day: str | None = None,
) -> str:
    from trading_pulse.agent.dryrun_agent import monthly_target_parts, risk_profile_parts
    from trading_pulse.core.schedule_tz import ISRAEL, utc_hhmm_to_zone
    from trading_pulse.telegram.telegram_format import _heartbeat_marked_parts

    equity = float(state.get("equity", getattr(cfg, "initial_capital", 0)))
    profile = risk_profile_parts(cfg, equity)
    marked = _heartbeat_marked_parts(state, equity)

    rows: list[tuple[str, str, str]] = [
        ("הון בספרים", fmt_money_plain(equity), ""),
    ]
    if marked:
        rows.append(("שווי משוער", fmt_money_plain(marked["marked"]), ""))
        ur = marked["unrealized"]
        ur_label = "רווח עתידי" if ur > 0 else ("הפסד עתידי" if ur < 0 else "עתידי")
        rows.append((ur_label, fmt_money(ur, signed=True), _pnl_class(ur)))

    rows.extend(
        [
            ("פרופיל", str(profile["label"]), ""),
            (
                "השקעה מקסימלית",
                f"עד {profile['max_deploy_pct']}% ({fmt_money_plain(profile['max_deploy_usd'], whole=True)})",
                "",
            ),
            (
                "עסקאות",
                f"עד {profile['max_trades']} · כ-{fmt_money_plain(profile['per_trade_usd'], whole=True)} לעסקה",
                "",
            ),
        ]
    )

    m = monthly_target_parts(cfg, state)
    pnl = m["month_pnl"]
    pnl_label = "רווח החודש" if pnl > 0 else ("הפסד החודש" if pnl < 0 else "חודש")
    month_pct = float(m.get("month_pnl_pct") or 0)
    pnl_s = f"{fmt_money(pnl, signed=True)} ({fmt_pct(month_pct)})"
    gap = m["gap_usd"]
    gap_label = "מעל היעד" if gap <= 0 else "נותר ליעד"
    rows.extend(
        [
            ("יעד חודשי", fmt_money_plain(m["target_usd"], whole=True), ""),
            ("נוכחי", fmt_money_plain(m["equity"]), ""),
            (pnl_label, pnl_s, _pnl_class(pnl)),
            (gap_label, fmt_money_plain(abs(gap), whole=True), ""),
            ("ימי מסחר שנותרו", str(int(m["trading_days_left"])), "muted"),
        ]
    )

    footer = ""
    if market_day:
        plan_il = str(getattr(cfg, "portfolio_review_time", "15:00"))
        report_utc = str(cfg.market_close_sim_time)
        report_il = utc_hhmm_to_zone(report_utc, ISRAEL) or report_utc
        rows.append(("סקירה", f"{plan_il} ישראל", "muted"))
        rows.append(("דוח", f"{report_il} ישראל ({report_utc} UTC)", "muted"))
    else:
        footer = (
            f"וול סטריט סגורה · תוכנית הבאה לקראת {next_trading_day}"
            if next_trading_day
            else "וול סטריט סגורה · אין מסחר היום"
        )

    return wrap_card_html("הסוכן חי", _kv_table(rows), accent="green", footer=footer)


_STRATEGY_HE = {
    "method2": "נרות סיניים 2",
    "rising_three": "Rising Three",
    "rising_three_methods": "Rising Three",
    "relative_strength": "חוזק יחסי",
    "vcp_breakout": "VCP",
    "trend_pullback": "תיקון במגמה",
    "score": "מומנטום",
    "score_momentum": "מומנטום",
}


def strategy_ids_he(strategies: list[Any] | None) -> list[str]:
    out: list[str] = []
    for s in strategies or []:
        key = str(s or "").strip()
        if not key:
            continue
        out.append(_STRATEGY_HE.get(key, key))
    return out


def _weekly_symbol_names(result: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in result.get("symbols") or []:
        if isinstance(item, dict):
            sym = str(item.get("symbol") or "").strip()
        else:
            sym = str(item).strip()
        if sym:
            names.append(sym)
    return names


def html_weekly_watchlist(result: dict[str, Any]) -> str:
    """Weekly universe scan summary as labeled HTML card."""
    week = str(result.get("week") or "")
    selected = int(result.get("selected") or 0)
    scanned = int(result.get("scanned") or 0)
    universe = int(result.get("universe_size") or 0)
    strategies = list(result.get("strategies_used") or [])
    strategy_hits = int(result.get("strategy_hit_symbols") or 0)
    sym_names = _weekly_symbol_names(result)
    preview = sym_names[:10]
    more = max(0, len(sym_names) - len(preview))

    rank_bits = ["מומנטום", "תנודתיות", "נפח"]
    if strategies:
        rank_bits.append("אותות אסטרטגיה")

    kv: list[tuple[str, str, str]] = [
        ("שבוע", week or "—", ""),
        ("נסרקו בהצלחה", f"{scanned} מתוך {universe}", ""),
        ("נבחרו לרשימה", str(selected), ""),
        ("דירוג לפי", " · ".join(rank_bits), "muted"),
    ]
    if strategies:
        he = strategy_ids_he(strategies)
        kv.append(("עם אות אסטרטגיה", f"{strategy_hits} מתוך {selected}", ""))
        kv.append(("שיטות שזוהו", " · ".join(he) if he else "—", "muted"))

    parts = [_kv_table(kv)]
    if preview:
        parts.append("<h2>Top 10 ברשימה</h2>")
        rows = [
            [(str(i + 1), ""), (sym, "sym")]
            for i, sym in enumerate(preview)
        ]
        parts.append(_table(["#", "סימול"], rows, numeric_cols={0}))
        if more:
            parts.append(
                f'<p class="foot">ועוד {more} מניות ברשימה המלאה — דשבורד או פקודת <b>מניות</b></p>'
            )

    parts.append("<h2>דוגמאות לעריכת הרשימה</h2>")
    parts.append('<div class="chips">')
    for c in ("הוסף SYMBOL", "הסר SYMBOL", "מניות"):
        parts.append(f'<span class="chip">{_esc(c)}</span>')
    parts.append("</div>")

    return wrap_card_html(
        f"רשימת מסחר לשבוע {week}",
        "".join(parts),
        footer=(
            "התוכנית היומית סורקת רק את הרשימה הזו · "
            "סריקה אוטומטית: יום ראשון ~09:00 ישראל"
        ),
    )


_VERDICT_HE = {
    "hold": "החזק",
    "sell": "מכור",
    "swap": "החלף",
    "take_profit": "ממש רווח",
}


def html_plan(plan: dict[str, Any]) -> str:
    """Evening plan as labeled HTML tables (readable on phone)."""
    day = str(plan.get("for_trading_day") or "")
    free = float(plan.get("available_capital_usd") or 0)
    invested = float(plan.get("deployed_capital_usd") or 0)
    equity = float(plan.get("equity_snapshot") or 0)
    holdings = list(plan.get("holdings") or [])
    actions = list(plan.get("holding_actions") or [])
    recs = list(plan.get("recommendations") or [])
    held = {str(h.get("symbol")) for h in holdings}
    new_recs = [r for r in recs if str(r.get("symbol")) not in held]
    action_by = {str(a.get("symbol")): a for a in actions}
    buy_syms = {str(r.get("symbol")) for r in new_recs}

    kv: list[tuple[str, str, str]] = [
        ("יום מסחר", day or "—", ""),
        ("מזומן פנוי", fmt_money_plain(free, whole=True), ""),
        ("מושקע", fmt_money_plain(invested, whole=True), ""),
        ("הון", fmt_money_plain(equity, whole=True), ""),
    ]
    monthly = str(plan.get("monthly_target_summary") or "").strip()
    if monthly:
        # Keep one short line — avoid wall of monthly prose
        kv.append(("יעד חודשי", monthly[:80], "muted"))

    parts = [_kv_table(kv)]

    if holdings:
        parts.append("<h2>בתיק עכשיו</h2>")
        rows = []
        for i, h in enumerate(holdings[:8]):
            sym = str(h.get("symbol") or "?")
            cap = float(h.get("capital_usd") or 0)
            a = action_by.get(sym) or {}
            verdict = str(a.get("verdict") or "hold")
            pnl = a.get("pnl_pct")
            if pnl is None:
                pnl = h.get("unrealized_pnl_pct")
            pnl_f = float(pnl) if pnl is not None else 0.0
            rows.append(
                [
                    (str(i + 1), ""),
                    (sym, "sym"),
                    (strategy_col(h), "muted"),
                    (fmt_money_plain(cap, whole=True), ""),
                    (fmt_pct(pnl_f) if pnl is not None else "—", _pnl_class(pnl_f)),
                    (_VERDICT_HE.get(verdict, verdict), ""),
                ]
            )
        parts.append(
            _table(
                ["#", "סימול", "שיטה", "מושקע", "מהכניסה", "המלצה"],
                rows,
                numeric_cols={0, 3, 4},
            )
        )
        parts.append(
            '<p class="foot">«הכל» לא מוכר ולא מחליף — רק קניות ממזומן</p>'
        )

    manual = [
        a
        for a in actions
        if str(a.get("verdict")) in {"sell", "swap", "take_profit"}
        and str(a.get("symbol") or "") in held
    ]
    if manual:
        parts.append("<h2>מומלץ ידנית (לא ב«הכל»)</h2>")
        rows = []
        chips_manual: list[str] = []
        for a in manual[:6]:
            sym = str(a.get("symbol") or "")
            verdict = str(a.get("verdict"))
            if verdict == "swap":
                to_sym = str(a.get("swap_to") or "")
                if to_sym in buy_syms:
                    cmd = f"מכור {sym}"
                    tip = f"לפנות מקום (לא החלף ל־{to_sym} — כבר מאושרת ממזומן)"
                else:
                    cmd = f"החלף {sym} {to_sym}"
                    tip = f"החלף → {to_sym}"
            else:
                cmd = f"מכור {sym}"
                tip = "מכירה למזומן"
            chips_manual.append(cmd)
            rows.append(
                [
                    (sym, "sym"),
                    (_VERDICT_HE.get(verdict, verdict), ""),
                    (tip, "muted"),
                    (cmd, "sym"),
                ]
            )
        parts.append(
            _table(
                ["סימול", "פעולה", "הסבר", "פקודה להעתקה"],
                rows,
                numeric_cols=set(),
            )
        )
        parts.append('<div class="chips">')
        for c in chips_manual:
            parts.append(f'<span class="chip">{_esc(c)}</span>')
        parts.append("</div>")

    if new_recs:
        parts.append("<h2>קניות חדשות ממזומן</h2>")
        rows = []
        for i, r in enumerate(new_recs[:8]):
            sym = str(r.get("symbol") or "?")
            cap = float(r.get("capital_usd") or 0)
            score = r.get("score")
            score_s = f"{float(score):.1f}" if score is not None else "—"
            strat = str(r.get("strategy") or r.get("strategy_id") or "")
            entry = "בפתיחה"
            if strat == "method2":
                side = str(r.get("side") or "LONG").upper()
                entry = "פריצה בלבד" + (" · שורט" if side == "SHORT" else "")
            rows.append(
                [
                    (str(i + 1), ""),
                    (sym, "sym"),
                    (strategy_col(r), "muted"),
                    (fmt_money_plain(cap, whole=True), ""),
                    (score_s, ""),
                    (entry, "muted"),
                ]
            )
        parts.append(
            _table(
                ["#", "סימול", "שיטה", "סכום", "ציון", "כניסה"],
                rows,
                numeric_cols={0, 3, 4},
            )
        )
        if plan.get("fallback_pick"):
            parts.append(
                '<p class="foot">אין מניה מעל סף האיכות — מוצגת הטובה ביותר (לשיקולך)</p>'
            )
    elif holdings:
        parts.append("<h2>קניות חדשות</h2>")
        parts.append('<p class="foot">אין קניות חדשות ממזומן היום</p>')

    parts.append("<h2>איך לאשר</h2>")
    parts.append('<div class="chips">')
    if new_recs:
        parts.append(f'<span class="chip">{_esc("הכל")}</span>')
        parts.append(
            '<p class="foot">שלח <b>הכל</b> — יחלק את המזומן על הקניות החדשות</p>'
        )
    else:
        parts.append('<p class="foot">אין קניות ממזומן לאשר · פעולות ידניות בצ׳יפים למעלה</p>')
    parts.append("</div>")

    parts.append("<h2>לוח זמנים (מידע — לא פקודות)</h2>")
    parts.append(
        '<p class="foot">מחר בפתיחה — כניסת קניות שאושרו · בערב — דוח יומי · '
        "גרף + פרטים בתמונה לכל מניה בהודעות הבאות (כיתוב קצר)</p>"
    )

    return wrap_card_html(f"תוכנית למחר · {day}", "".join(parts))


def html_recommendation(
    rec: dict[str, Any],
    idx: int,
    trading_day: str,
    *,
    signal_lines: list[str] | None = None,
    held: bool = False,
) -> str:
    """Labeled details under a plan chart (baked into PNG — not a Telegram caption)."""
    sym = str(rec.get("symbol") or "?")
    day = str(trading_day or "")
    draft = float(rec.get("capital_usd") or 0)
    price = float(rec.get("entry_ref_price") or 0)
    sl_frac = float(rec.get("stop_loss_pct") or 0)
    tp_frac = float(rec.get("take_profit_pct") or 0)
    # stop_loss_pct is stored positive (e.g. 0.12) — show leading minus.
    sl_pct = -abs(sl_frac * 100) if sl_frac else 0.0
    tp_pct = abs(tp_frac * 100) if tp_frac else 0.0
    sl_price = float(rec.get("floor_price") or rec.get("stop_loss_price") or 0)
    tp_price = float(rec.get("take_profit_price") or 0)
    score = rec.get("score")

    kv: list[tuple[str, str, str]] = [
        ("יום מסחר", day or "—", ""),
        ("הצעה", fmt_money_plain(draft, whole=True), ""),
        ("מחיר ייחוס", fmt_money_plain(price, digits=2), ""),
    ]
    if score is not None:
        kv.append(("ציון", f"{float(score):.1f}", ""))
    kv.extend(
        [
            (
                "מחיר תחתון",
                f"{fmt_money_plain(sl_price, digits=2)} ({fmt_pct(sl_pct, digits=0)})",
                "neg" if sl_pct < 0 else "",
            ),
            (
                "יעד רווח",
                f"{fmt_money_plain(tp_price, digits=2)} ({fmt_pct(tp_pct, digits=0)})",
                "pos" if tp_pct > 0 else "",
            ),
        ]
    )

    parts = [_kv_table(kv)]
    parts.append('<p class="foot">מכירה אוטומטית מתחת למחיר התחתון</p>')

    strat = str(rec.get("strategy") or "")
    if strat == "method2":
        side = str(rec.get("side") or "LONG").upper()
        side_he = "שורט" if side == "SHORT" else "לונג"
        trig = str(rec.get("trigger") or "")
        entry = float(rec.get("method2_entry_ref") or rec.get("entry_ref_price") or 0)
        stop = float(rec.get("method2_stop_ref") or rec.get("stop_loss_price") or 0)
        parts.append("<h2>נרות סיניים 2</h2>")
        parts.append(
            _kv_table(
                [
                    ("כיוון", side_he, ""),
                    ("טריגר", trig or "—", "muted"),
                    ("פריצה", fmt_money_plain(entry, digits=2), ""),
                    ("סטופ", fmt_money_plain(stop, digits=2), ""),
                ]
            )
        )
        parts.append('<p class="foot">כניסה רק אם נפרצת הרמה</p>')
    elif strat == "rising_three_methods":
        weak = " (חלש)" if rec.get("pattern_weak") else ""
        parts.append(f'<p class="foot">נרות · Rising Three Methods{weak}</p>')

    if held:
        parts.append('<p class="foot"><b>כבר בתיק — לא נקנה שוב</b></p>')

    clean_signals = [s.strip() for s in (signal_lines or []) if str(s).strip()][:4]
    if clean_signals:
        parts.append("<h2>אותות</h2>")
        for line in clean_signals:
            parts.append(f'<p class="foot">{_esc(line)}</p>')

    headlines = list(rec.get("news_headlines") or [])[:1]
    if headlines:
        title = str(headlines[0].get("title") or "").strip()
        if title:
            parts.append("<h2>חדשות</h2>")
            parts.append(f'<p class="foot">{_esc(title[:100])}</p>')
    summary = str(rec.get("news_summary") or "").strip()
    if summary:
        parts.append(f'<p class="foot">{_esc(summary[:140])}</p>')

    return wrap_card_html(f"#{idx} {sym}", "".join(parts))


def card_png_from_html(
    html_doc: str,
    *,
    width: int,
    height: int = 2600,
    pil_fallback_fn=None,
) -> bytes:
    """Render HTML card; call pil_fallback_fn() only if browser fails."""
    png = try_render_html_to_png(html_doc, width=width, height=height)
    if png:
        return png
    if pil_fallback_fn is not None:
        logging.warning("HTML→PNG failed; using PIL fallback")
        return pil_fallback_fn()
    raise RuntimeError("HTML→PNG failed")
