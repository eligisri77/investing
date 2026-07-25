"""HTML table cards + leading-sign formatters for Telegram."""

from __future__ import annotations

from trading_pulse.telegram.html_tables import (
    fmt_money,
    fmt_pct,
    html_allocation,
    html_daily_report,
    html_entry,
    html_heartbeat,
    html_intraday,
    html_portfolio,
    wrap_card_html,
)
from trading_pulse.telegram.reply_cards import (
    card_allocation_prompt,
    card_daily_report,
    card_entry,
    card_heartbeat,
    card_intraday_monitor,
    card_portfolio,
)


def test_fmt_pct_leading_sign():
    assert fmt_pct(-3.5) == "-3.5%"
    assert fmt_pct(3.5) == "+3.5%"
    assert fmt_pct(0) == "0.0%"
    assert fmt_pct(None) == "—"


def test_fmt_money_leading_sign():
    assert fmt_money(-4.0, signed=True) == "-$4.00"
    assert fmt_money(1.67, signed=True) == "+$1.67"
    assert fmt_money(0, signed=True) == "$0.00"
    assert fmt_money(-11.0, signed=True, whole=True) == "-$11"
    assert fmt_money(None, signed=True) == "—"


def test_html_intraday_has_column_headers():
    from trading_pulse.agent.intraday_monitor import IntradayReport

    report = IntradayReport(
        checked_at="now",
        holdings=[
            {
                "symbol": "ISRG",
                "last": 331.09,
                "pnl_pct": -4.5,
                "day_change_pct": -2.2,
                "capital_usd": 116,
                "floor_price": 303.97,
                "strategy_id": "score",
            }
        ],
    )
    doc = html_intraday(report)
    assert "מהכניסה" in doc
    assert "3.5%+" not in doc  # not this value
    assert "-4.5%" in doc
    assert "מושקע" in doc
    assert "ISRG" in doc
    assert "רף יציאה" in doc
    assert "היום" in doc


def test_html_daily_report_leading_signs_and_headers():
    doc = html_daily_report(
        {
            "trading_day": "2026-07-22",
            "equity_before": 993.59,
            "equity_after": 991.52,
            "pnl_usd": -2.07,
            "unrealized_pnl_usd": -24.38,
            "equity_marked_usd": 967.14,
            "held_eod": [
                {
                    "symbol": "LCID",
                    "capital_usd": 116,
                    "days_held": 3,
                    "unrealized_pnl_usd": -4.77,
                    "unrealized_pnl_pct": -4.1,
                    "strategy_id": "score",
                }
            ],
            "executed": [
                {
                    "symbol": "VLO",
                    "pnl_usd": -2.07,
                    "pnl_pct": -1.4,
                    "days_held": 0,
                    "exit_reason": "user_sell",
                    "manual_exit": True,
                    "strategy_id": "method2",
                }
            ],
        }
    )
    assert "שינוי ממומש היום" in doc
    assert "-$2.07" in doc
    assert "רווח עתידי (לא ממומש)" in doc
    assert "-$24.38" in doc
    assert "מהכניסה" in doc
    assert "-4.1%" in doc
    assert "רווח פתוח" in doc
    assert "נסגרו — מכירה ידנית" in doc
    assert "-1.4%" in doc
    assert "LCID" in doc
    assert "VLO" in doc


def test_html_portfolio_labels_and_leading_signs():
    doc = html_portfolio(
        {
            "equity": 986.68,
            "cash_usd": 20,
            "open_marked_usd": 1021,
            "unrealized_pnl_usd": 34,
            "total_realized_pnl": -13.32,
            "open_positions": [
                {
                    "symbol": "LABD",
                    "status": "holding",
                    "capital_usd": 333,
                    "entry_price": 7.1,
                    "marked_value_usd": 322,
                    "unrealized_pnl_usd": -11,
                    "entry_at": "2026-07-08T17:20:00+00:00",
                    "strategy_id": "score",
                },
                {
                    "symbol": "RIVN",
                    "status": "holding",
                    "capital_usd": 333,
                    "entry_price": 15.66,
                    "marked_value_usd": 386,
                    "unrealized_pnl_usd": 52,
                    "entry_at": "2026-07-08T17:20:00+00:00",
                    "strategy_id": "relative_strength",
                },
            ],
        }
    )
    assert "תיק השקעות" in doc
    assert "מזומן פנוי" in doc
    assert "רווח פתוח" in doc
    assert "+$34" in doc
    assert "רווח ממומש" in doc
    assert "-$13.32" in doc
    assert "בתיק עכשיו" in doc
    assert "מחיר כניסה" in doc
    assert "-$11" in doc
    assert "+$52" in doc
    assert "LABD" in doc
    assert "RIVN" in doc
    assert "דוגמאות לפעולות בתיק" in doc


def test_html_allocation_headers_and_chips():
    doc = html_allocation(
        {"equity_snapshot": 970, "recommendations": []},
        [
            {
                "id": 1,
                "title": "שווה",
                "description": "חלוקה שווה",
                "full_invest": True,
                "equity_usd": 970,
                "holdings": [{"symbol": "ISRG", "capital_usd": 116}],
                "new_entries": [{"symbol": "CROX", "capital_usd": 106}],
                "deployed_total_usd": 970,
                "reserve_usd": 0,
            },
            {
                "id": 4,
                "title": "חצי",
                "full_invest": False,
                "equity_usd": 970,
                "holdings": [],
                "new_entries": [{"symbol": "CELH", "capital_usd": 53}],
                "deployed_total_usd": 859,
                "reserve_usd": 111,
            },
        ],
        trading_day="2026-07-24",
    )
    assert "שלב 2 — חלוקת הון" in doc
    assert "יום מסחר" in doc
    assert "פנוי לחלוקה" in doc
    assert "השוואת אופציות" in doc
    assert "אופציה" in doc
    assert "ח1" in doc
    assert "ח4" in doc
    assert "CROX" in doc
    assert "בחר אחת" in doc


def test_html_entry_column_headers():
    doc = html_entry(
        [
            {
                "symbol": "MPC",
                "capital_usd": 296,
                "entry_price": 319.0,
                "strategy_id": "relative_strength",
            },
            {
                "symbol": "ARWR",
                "capital_usd": 147,
                "entry_price": 89.25,
                "strategy_id": "score",
            },
        ],
        trading_day="2026-07-22",
        subtitle="קניה בוקר",
    )
    assert "קניה בוקר · 2026-07-22" in doc
    assert "שיטת כניסה" in doc
    assert "מחיר כניסה" in doc
    assert "סכום" in doc
    assert "MPC" in doc
    assert "$296" in doc
    assert "$319.00" in doc


def test_html_heartbeat_kv_labels_and_leading_signs():
    from trading_pulse.agent.dryrun_agent import AgentConfig, apply_risk_profile

    cfg = AgentConfig()
    cfg.risk_profile = "speculative"
    cfg.monthly_target_usd = 1100.0
    apply_risk_profile(cfg)
    doc = html_heartbeat(
        cfg,
        {
            "equity": 969.81,
            "month_start_equity": 1000.0,
            "open_positions": [],
        },
        market_day=True,
    )
    assert "הסוכן חי" in doc
    assert "הון בספרים" in doc
    assert "פרופיל" in doc
    assert "השקעה מקסימלית" in doc
    assert "יעד חודשי" in doc
    assert "הפסד החודש" in doc
    assert "-$30.19" in doc
    assert "-3.0%" in doc
    assert "נותר ליעד" in doc
    assert "תוכנית" in doc
    assert "דוח" in doc


def test_html_heartbeat_closed_market_footer():
    from trading_pulse.agent.dryrun_agent import AgentConfig

    doc = html_heartbeat(
        AgentConfig(),
        {"equity": 1000.0, "month_start_equity": 1000.0, "open_positions": []},
        market_day=False,
        next_trading_day="2026-07-27",
    )
    assert "וול סטריט סגורה" in doc
    assert "2026-07-27" in doc
    assert 'class="k">תוכנית</td>' not in doc
    assert 'class="k">דוח</td>' not in doc


def test_card_intraday_html_png():
    from trading_pulse.agent.intraday_monitor import IntradayReport

    report = IntradayReport(
        checked_at="now",
        holdings=[
            {
                "symbol": "NET",
                "last": 262.0,
                "pnl_pct": -5.8,
                "day_change_pct": -3.7,
                "capital_usd": 200,
                "floor_price": 247.9,
                "strategy_id": "relative_strength",
            }
        ],
    )
    png = card_intraday_monitor(report)
    assert png.startswith(b"\x89PNG")
    assert len(png) > 2000


def test_card_daily_report_html_png():
    png = card_daily_report(
        {
            "trading_day": "2026-07-22",
            "equity_before": 993.59,
            "equity_after": 991.52,
            "pnl_usd": -2.07,
            "unrealized_pnl_usd": -24.38,
            "held_eod": [
                {
                    "symbol": "LCID",
                    "capital_usd": 116,
                    "days_held": 3,
                    "unrealized_pnl_usd": -4.77,
                    "unrealized_pnl_pct": -4.1,
                    "strategy_id": "score",
                }
            ],
            "executed": [],
        }
    )
    assert png.startswith(b"\x89PNG")


def test_card_portfolio_html_png():
    png = card_portfolio(
        {
            "equity": 986.68,
            "cash_usd": 20,
            "open_marked_usd": 1021,
            "unrealized_pnl_usd": 34,
            "total_realized_pnl": -13.32,
            "open_positions": [
                {
                    "symbol": "LABD",
                    "status": "holding",
                    "capital_usd": 333,
                    "entry_price": 7.1,
                    "marked_value_usd": 322,
                    "unrealized_pnl_usd": -11,
                    "entry_at": "2026-07-08T17:20:00+00:00",
                }
            ],
        }
    )
    assert png.startswith(b"\x89PNG")
    assert len(png) > 2000


def test_card_allocation_html_png():
    png = card_allocation_prompt(
        {"equity_snapshot": 970},
        [
            {
                "id": 1,
                "title": "שווה",
                "full_invest": True,
                "equity_usd": 970,
                "holdings": [],
                "new_entries": [{"symbol": "CROX", "capital_usd": 200}],
                "deployed_total_usd": 200,
                "reserve_usd": 0,
            }
        ],
        trading_day="2026-07-24",
    )
    assert png.startswith(b"\x89PNG")
    assert len(png) > 1500


def test_card_entry_html_png():
    png = card_entry(
        [{"symbol": "MPC", "capital_usd": 296, "entry_price": 319.0}],
        trading_day="2026-07-22",
        subtitle="קניה בוקר",
    )
    assert png.startswith(b"\x89PNG")
    assert len(png) > 1500


def test_card_heartbeat_html_png():
    from trading_pulse.agent.dryrun_agent import AgentConfig, apply_risk_profile

    cfg = AgentConfig()
    cfg.risk_profile = "speculative"
    apply_risk_profile(cfg)
    png = card_heartbeat(
        cfg,
        {"equity": 969.81, "month_start_equity": 1000.0, "open_positions": []},
        market_day=True,
    )
    assert png.startswith(b"\x89PNG")
    assert len(png) > 2000


def test_wrap_card_contains_rtl():
    doc = wrap_card_html("כותרת", "<p>גוף</p>")
    assert 'dir="rtl"' in doc
    assert "כותרת" in doc
