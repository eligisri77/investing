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
    html_offer_cubes,
    html_plan,
    html_portfolio,
    html_recommendation,
    html_weekly_watchlist,
    wrap_card_html,
)
from trading_pulse.telegram.reply_cards import (
    card_allocation_prompt,
    card_daily_report,
    card_entry,
    card_from_plan_summary,
    card_heartbeat,
    card_intraday_monitor,
    card_portfolio,
    card_weekly_watchlist,
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
    assert "סקירה" in doc
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
    assert 'class="k">סקירה</td>' not in doc
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


def test_html_offer_cubes_contains_titles_blurbs_and_wrap_title():
    cubes = [
        {
            "title": "ציון ותנודתיות",
            "blurb": "דירוג מול הרשימה וכמה המניה זזה ביום.",
            "value": "דירוג #1 · ציון 13.0",
        },
        {
            "title": "נפח",
            "blurb": "האם יש עניין בשוק מעבר לתנועת מחיר בלבד.",
            "value": "3.33× מהממוצע · גבוה",
            "wide": "1",
        },
    ]
    doc = html_offer_cubes(
        {"symbol": "RBLX", "score": 13.0},
        position_no=1,
        total=5,
        cash_free=1000.0,
        suggested_usd=200.0,
        cubes=cubes,
    )
    assert 'dir="rtl"' in doc
    assert "<h1" in doc and "הצעה 1/5: RBLX" in doc
    assert "ציון 13.0" in doc
    assert 'class="cube-title"' in doc
    assert "ציון ותנודתיות" in doc
    assert "נפח" in doc
    assert 'class="cube-blurb"' in doc
    assert "דירוג מול הרשימה" in doc
    assert "עניין בשוק" in doc
    assert 'class="cube-value"' in doc
    assert "דירוג #1" in doc
    assert 'class="cube wide"' in doc
    assert "מזומן פנוי" in doc
    assert "הצעה בלבד" in doc


def test_html_weekly_watchlist_labels_and_hebrew_strategies():
    doc = html_weekly_watchlist(
        {
            "week": "W30-2026",
            "scanned": 139,
            "universe_size": 420,
            "selected": 60,
            "symbols": ["CLF", "TSLL", "WOLF"] + [f"S{i}" for i in range(57)],
            "strategies_used": ["method2", "relative_strength", "rising_three", "vcp_breakout"],
            "strategy_hit_symbols": 47,
        }
    )
    assert "נסרקו בהצלחה" in doc
    assert "139 מתוך 420" in doc
    assert "נבחרו לרשימה" in doc
    assert "נרות סיניים 2" in doc
    assert "חוזק יחסי" in doc
    assert "Top 10 ברשימה" in doc
    assert "CLF" in doc
    assert "דוגמאות לעריכת הרשימה" in doc
    assert "09:00 ישראל" in doc


def test_card_weekly_watchlist_html_png():
    png = card_weekly_watchlist(
        {
            "week": "W30-2026",
            "scanned": 139,
            "universe_size": 420,
            "selected": 60,
            "symbols": ["CLF", "TSLL", "WOLF", "LMT", "QS"],
            "strategies_used": ["method2"],
            "strategy_hit_symbols": 3,
        }
    )
    assert png.startswith(b"\x89PNG")
    assert len(png) > 2000


def test_html_plan_labels_manual_and_new_buys():
    doc = html_plan(
        {
            "for_trading_day": "2026-07-27",
            "available_capital_usd": 260,
            "deployed_capital_usd": 708,
            "equity_snapshot": 968,
            "monthly_target_summary": "יעד $2000 · נוכחי $968",
            "holdings": [
                {
                    "symbol": "NET",
                    "capital_usd": 200,
                    "strategy_id": "relative_strength",
                    "unrealized_pnl_pct": -5.9,
                },
                {"symbol": "ARWR", "capital_usd": 147, "unrealized_pnl_pct": -4.1},
            ],
            "holding_actions": [
                {"symbol": "NET", "verdict": "sell", "pnl_pct": -5.9, "capital_usd": 200},
                {
                    "symbol": "ARWR",
                    "verdict": "swap",
                    "swap_to": "CLF",
                    "pnl_pct": -4.1,
                },
            ],
            "recommendations": [
                {"symbol": "CLF", "capital_usd": 87, "score": 16.3, "strategy_id": "score"},
                {"symbol": "TSLL", "capital_usd": 87, "score": 10.3, "strategy_id": "score"},
            ],
        }
    )
    assert "יום מסחר" in doc
    assert "מזומן פנוי" in doc
    assert "בתיק עכשיו" in doc
    assert "לא תויגה" in doc
    assert "-5.9%" in doc
    assert "מומלץ ידנית" in doc
    assert "מכור NET" in doc
    assert "כבר מאושרת" in doc
    assert "קניות חדשות ממזומן" in doc
    assert "CLF" in doc
    assert "איך לאשר" in doc
    assert "הכל" in doc
    assert "לוח זמנים" in doc


def test_html_plan_swap_tip_when_target_not_in_buys():
    """Swap target not among cash buys → החלף tip (not sell-to-make-room)."""
    doc = html_plan(
        {
            "for_trading_day": "2026-07-27",
            "available_capital_usd": 100,
            "deployed_capital_usd": 800,
            "equity_snapshot": 900,
            "holdings": [{"symbol": "RIVN", "capital_usd": 200, "unrealized_pnl_pct": -3.0}],
            "holding_actions": [
                {
                    "symbol": "RIVN",
                    "verdict": "swap",
                    "swap_to": "NVDA",
                    "pnl_pct": -3.0,
                }
            ],
            "recommendations": [
                {"symbol": "TSLA", "capital_usd": 100, "score": 12.0, "strategy_id": "score"},
            ],
        }
    )
    assert "החלף RIVN NVDA" in doc
    assert "החלף → NVDA" in doc
    assert "כבר מאושרת" not in doc
    assert "מכור RIVN" not in doc


def test_html_plan_no_new_buys_path():
    """Holdings but no fresh cash buys → empty buys section + no הכל chip."""
    doc = html_plan(
        {
            "for_trading_day": "2026-07-27",
            "available_capital_usd": 5,
            "deployed_capital_usd": 990,
            "equity_snapshot": 995,
            "holdings": [
                {
                    "symbol": "LABD",
                    "capital_usd": 333,
                    "strategy_id": "score",
                    "unrealized_pnl_pct": 1.2,
                }
            ],
            "holding_actions": [
                {"symbol": "LABD", "verdict": "hold", "pnl_pct": 1.2},
            ],
            # Already held — not a "new" cash buy
            "recommendations": [
                {"symbol": "LABD", "capital_usd": 333, "score": 9.0, "strategy_id": "score"},
            ],
        }
    )
    assert "אין קניות חדשות ממזומן היום" in doc
    assert "<h2>קניות חדשות</h2>" in doc
    assert "<h2>קניות חדשות ממזומן</h2>" not in doc
    assert "אין קניות ממזומן לאשר" in doc
    assert 'class="chip">הכל</span>' not in doc
    assert "+1.2%" in doc


def test_html_plan_method2_entry_and_fallback_note():
    doc = html_plan(
        {
            "for_trading_day": "2026-07-27",
            "available_capital_usd": 200,
            "deployed_capital_usd": 0,
            "equity_snapshot": 200,
            "holdings": [],
            "holding_actions": [],
            "fallback_pick": True,
            "recommendations": [
                {
                    "symbol": "SOXL",
                    "capital_usd": 100,
                    "score": 8.0,
                    "strategy": "method2",
                    "side": "SHORT",
                },
            ],
        }
    )
    assert "פריצה בלבד" in doc
    assert "שורט" in doc
    assert "אין מניה מעל סף האיכות" in doc
    assert "הכל" in doc


def test_card_plan_html_png():
    png = card_from_plan_summary(
        {
            "for_trading_day": "2026-07-27",
            "available_capital_usd": 260,
            "deployed_capital_usd": 708,
            "equity_snapshot": 968,
            "holdings": [{"symbol": "NET", "capital_usd": 200}],
            "recommendations": [{"symbol": "CLF", "capital_usd": 87}],
        }
    )
    assert png.startswith(b"\x89PNG")
    assert len(png) > 2000


def test_html_recommendation_leading_minus_and_labels():
    doc = html_recommendation(
        {
            "symbol": "CLF",
            "capital_usd": 87,
            "entry_ref_price": 10.96,
            "stop_loss_pct": 0.12,
            "take_profit_pct": 0.25,
            "floor_price": 9.64,
            "take_profit_price": 13.70,
            "score": 16.3,
            "strategy": "score",
            "strategy_id": "score_momentum",
            "entry_policy": "market_open",
        },
        1,
        "2026-07-27",
        signal_lines=["מומנטום חיובי"],
    )
    assert "יום מסחר" in doc
    assert "שיטת כניסה" in doc
    assert "מומנטום וציון" in doc or "מומנטום" in doc
    assert "מחיר תחתון" in doc
    assert "-12%" in doc
    assert "12%-" not in doc
    assert "(-12%)" not in doc or "-12%" in doc  # parenthesized with leading minus OK
    assert "+25%" in doc
    assert "הצעה" in doc
    assert "CLF" in doc
    assert "מומנטום חיובי" in doc
    assert 'class="detail"' in doc
    assert "font-size: 20px" in doc  # .detail readable on phone
