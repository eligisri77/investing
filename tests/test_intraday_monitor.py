"""Tests for intraday market monitoring."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from unittest.mock import patch

import pandas as pd

from trading_pulse.agent.intraday_monitor import (
    IntradayReport,
    PositionAlert,
    analyze_position,
    build_suggestions,
    filter_cooled_down,
    is_within_market_hours,
)


@dataclass
class FakeCfg:
    stop_loss_pct: float = 0.12
    take_profit_pct: float = 0.25
    max_open_positions: int = 4
    min_volume_ratio: float = 1.0
    market_open_sim_time: str = "13:30"
    market_close_sim_time: str = "20:20"
    intraday_cash_topup_min_usd: float = 20.0


def test_is_within_market_hours():
    cfg = FakeCfg()
    # Config times are UTC (naive args treated as UTC).
    inside = datetime(2026, 6, 17, 18, 0)
    outside = datetime(2026, 6, 17, 10, 0)
    assert is_within_market_hours(cfg, now=inside) is True
    assert is_within_market_hours(cfg, now=outside) is False
    # After configured close — still open on Israel wall clock, but closed in UTC window.
    after_close = datetime(2026, 6, 17, 21, 0)
    assert is_within_market_hours(cfg, now=after_close) is False


def test_analyze_near_stop():
    cfg = FakeCfg()
    pos = {"symbol": "SOXL", "entry_price": 100.0, "stop_loss_pct": 0.12, "take_profit_pct": 0.25}
    quote = {"last": 89.5, "open": 92.0, "change_pct": -2.7}
    alerts = analyze_position(pos, quote, cfg)
    kinds = {a.kind for a in alerts}
    assert "near_stop" in kinds


def test_analyze_intraday_drop():
    cfg = FakeCfg()
    pos = {"symbol": "LABU", "entry_price": 50.0, "stop_loss_pct": 0.12, "take_profit_pct": 0.25}
    quote = {"last": 47.0, "open": 50.0, "change_pct": -6.0}
    alerts = analyze_position(pos, quote, cfg)
    assert any(a.kind == "intraday_drop" for a in alerts)


def test_build_buy_skips_pending_plan_symbols():
    cfg = FakeCfg(max_open_positions=4)
    holdings: list[dict] = []
    scores = {
        "LABU": {"score": 14.0, "ret_5d_pct": 8.0, "vol_ratio": 1.5, "volume_ok": True},
        "NVDA": {"score": 12.0, "ret_5d_pct": 5.0, "vol_ratio": 1.2, "volume_ok": True},
    }
    suggestions = build_suggestions(cfg, holdings, scores, {}, {}, exclude_symbols={"LABU"})
    assert len(suggestions) == 1
    assert suggestions[0].symbol == "NVDA"


def test_build_buy_suggestion_when_slots_open():
    cfg = FakeCfg(max_open_positions=4)
    holdings = [{"symbol": "AMD", "entry_price": 100}]
    scores = {
        "AMD": {"score": 10.0, "ret_5d_pct": 3.0, "vol_ratio": 1.2, "volume_ok": True},
        "NVDA": {"score": 14.0, "ret_5d_pct": 8.0, "vol_ratio": 1.5, "volume_ok": True},
    }
    suggestions = build_suggestions(cfg, holdings, scores, {}, {})
    assert len(suggestions) == 1
    assert suggestions[0].kind == "buy"
    assert suggestions[0].symbol == "NVDA"


def test_build_swap_when_full_and_weak_holding():
    cfg = FakeCfg(max_open_positions=2)
    holdings = [
        {"symbol": "AMD", "entry_price": 100},
        {"symbol": "IONQ", "entry_price": 40},
    ]
    scores = {
        "AMD": {"score": 9.0, "ret_5d_pct": -1.0, "vol_ratio": 0.8, "volume_ok": False},
        "IONQ": {"score": 6.0, "ret_5d_pct": -4.0, "vol_ratio": 0.6, "volume_ok": False},
        "NVDA": {"score": 15.0, "ret_5d_pct": 10.0, "vol_ratio": 1.8, "volume_ok": True},
    }
    quotes = {"IONQ": {"change_pct": -3.5}}
    alerts = {"IONQ": [PositionAlert("IONQ", "intraday_drop", "test", severity=2)]}
    suggestions = build_suggestions(cfg, holdings, scores, quotes, alerts)
    assert any(s.kind == "swap" and s.swap_from == "IONQ" for s in suggestions)


def test_sell_recommended_on_heavy_loss():
    cfg = FakeCfg(max_open_positions=4)
    holdings = [{"symbol": "SOXL", "entry_price": 197.21}]
    quotes = {"SOXL": {"last": 168.0, "change_pct": -14.0}}
    alerts = {"SOXL": [PositionAlert("SOXL", "heavy_loss", "הפסד משמעותי", severity=2)]}
    suggestions = build_suggestions(cfg, holdings, {}, quotes, alerts)
    sells = [s for s in suggestions if s.kind == "sell"]
    assert len(sells) == 1
    assert sells[0].symbol == "SOXL"
    assert "ירידה חדה היום" in sells[0].message
    assert "ירדה" in sells[0].message


def test_sell_recommended_on_near_stop_without_scores():
    cfg = FakeCfg()
    holdings = [{"symbol": "MSTR", "entry_price": 100.0}]
    quotes = {"MSTR": {"last": 89.0, "change_pct": -5.0}}
    alerts = {"MSTR": [PositionAlert("MSTR", "near_stop", "קרוב לרף", severity=3)]}
    suggestions = build_suggestions(cfg, holdings, {}, quotes, alerts)
    sells = [s for s in suggestions if s.kind == "sell" and s.symbol == "MSTR"]
    assert len(sells) == 1
    msg = sells[0].message
    assert msg.startswith("המחיר קרוב לרף המכירה")
    assert "ירידה חדה" not in msg
    assert "ירדה" in msg
    assert "למכור את MSTR" in msg
    assert "במזומן" in msg
    assert not re.search(r"[+\-]\d+\.?\d*%", msg)


def test_sell_recommendation_includes_redeploy_swap():
    cfg = FakeCfg(max_open_positions=4)
    holdings = [{"symbol": "SOXL", "entry_price": 197.0, "capital_usd": 333.0}]
    quotes = {"SOXL": {"last": 168.0, "change_pct": -14.0}}
    alerts = {"SOXL": [PositionAlert("SOXL", "heavy_loss", "x", severity=2)]}
    scores = {"NVDA": {"score": 12.0, "ret_5d_pct": 8.0, "vol_ratio": 1.5, "volume_ok": True}}
    suggestions = build_suggestions(cfg, holdings, scores, quotes, alerts)
    swaps = [s for s in suggestions if s.kind == "swap" and s.swap_from == "SOXL"]
    assert len(swaps) == 1
    assert swaps[0].symbol == "NVDA"
    msg = swaps[0].message
    assert "$333" in msg
    assert "ולקנות במקומה NVDA" in msg
    assert "ירדה" in msg
    assert not re.search(r"[+\-]\d+\.?\d*%", msg)


def test_sell_recommendation_holds_cash_when_no_candidate():
    cfg = FakeCfg()
    holdings = [{"symbol": "SOXL", "entry_price": 197.0}]
    quotes = {"SOXL": {"last": 168.0, "change_pct": -14.0}}
    alerts = {"SOXL": [PositionAlert("SOXL", "heavy_loss", "x", severity=2)]}
    suggestions = build_suggestions(cfg, holdings, {}, quotes, alerts)
    sells = [s for s in suggestions if s.kind == "sell"]
    assert len(sells) == 1
    msg = sells[0].message
    assert "למכור את SOXL" in msg
    assert "במזומן" in msg
    assert "ירדה" in msg
    assert "מאז הקנייה" in msg
    assert not re.search(r"[+\-]\d+\.?\d*%", msg)


def test_format_intraday_howto_commands():
    from trading_pulse.agent.intraday_monitor import TradeSuggestion
    from trading_pulse.telegram.telegram_format import format_intraday_monitor

    report = IntradayReport(
        checked_at="now",
        holdings=[{"symbol": "LABD", "last": 10.0, "pnl_pct": 5.0, "day_change_pct": 1.0, "capital_usd": 250}],
        suggestions=[
            TradeSuggestion(
                kind="swap",
                symbol="PYPL",
                swap_from="LABD",
                message="החלף LABD ב-PYPL",
            ),
            TradeSuggestion(kind="buy", symbol="NVDA", message="ציון 12 · מומלץ ~$200"),
            TradeSuggestion(kind="sell", symbol="SOXL", message="ירידה חדה"),
        ],
    )
    text = format_intraday_monitor(report)
    assert "איך לבצע" in text
    assert "החלף LABD PYPL" in text
    assert "תקנה NVDA" in text
    assert "מכור SOXL" in text
    assert "מהכניסה" in text
    assert "+5.0%" in text
    assert "היום" in text
    assert "+1.0%" in text
    assert "העתק את הפקודה" in text


def test_format_intraday_bidi_safe_numbers_and_floor_loss():
    from trading_pulse.telegram.telegram_format import format_intraday_monitor

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
        floor_sells=[
            {
                "symbol": "LCID",
                "exit_price": 6.35,
                "floor_price": 6.48,
                "pnl_usd": -11.85,
            }
        ],
    )
    text = format_intraday_monitor(report)
    assert "<code>" in text
    assert "\u200e" in text  # LRM islands inside <code>
    assert "\u2212" in text  # unicode minus, not ASCII hyphen before %
    assert "מהכניסה" in text and "4.5%" in text
    assert "היום" in text and "2.2%" in text
    assert "מושקע" in text and text.index("מושקע") < text.index("$116")
    assert "שיטת כניסה · מומנטום וציון" in text
    assert "LCID" in text
    assert "הפסד" in text
    assert "11.85" in text
    assert "יציאה אוטומטית" in text
    assert "העתק את הפקודה" not in text
    # Negatives must not use ASCII hyphen-minus next to %/$
    assert not re.search(r"-\d+\.\d+%", text)
    assert not re.search(r"-\$", text)


def test_format_intraday_ticker_on_own_line():
    """Ticker never shares a line with $ / % (RTL BiDi scramble)."""
    from trading_pulse.telegram.telegram_format import format_intraday_monitor

    report = IntradayReport(
        checked_at="now",
        holdings=[
            {
                "symbol": "ISRG",
                "last": 331.09,
                "pnl_pct": -4.5,
                "day_change_pct": 1.0,
                "capital_usd": 116,
                "floor_price": 303.97,
            }
        ],
        floor_sells=[
            {
                "symbol": "LCID",
                "exit_price": 6.35,
                "floor_price": 6.48,
                "pnl_usd": -11.85,
            }
        ],
    )
    text = format_intraday_monitor(report)
    for line in text.splitlines():
        if "ISRG" in line or "LCID" in line:
            assert "$" not in line, line
            assert "%" not in line, line
            assert "מהכניסה" not in line
            assert "יציאה" not in line


def test_format_intraday_floor_sell_profit_and_watch_footer():
    from trading_pulse.agent.intraday_monitor import TradeSuggestion
    from trading_pulse.telegram.telegram_format import format_intraday_monitor

    profit_report = IntradayReport(
        checked_at="now",
        holdings=[],
        floor_sells=[
            {
                "symbol": "NVDA",
                "exit_price": 120.0,
                "floor_price": 100.0,
                "pnl_usd": 25.5,
            }
        ],
    )
    profit_text = format_intraday_monitor(profit_report)
    assert "רווח" in profit_text
    assert "+$25.50" in profit_text
    assert "הפסד" not in profit_text
    assert "יציאה אוטומטית" in profit_text

    watch_report = IntradayReport(
        checked_at="now",
        holdings=[
            {
                "symbol": "AAPL",
                "last": 190.0,
                "pnl_pct": 0.0,
                "day_change_pct": 0.0,
                "capital_usd": 50,
            }
        ],
        suggestions=[
            TradeSuggestion(kind="watch", symbol="AAPL", message="לעקוב אחרי התאוששות"),
        ],
    )
    watch_text = format_intraday_monitor(watch_report)
    assert "לעקוב" in watch_text
    assert "איך לבצע" not in watch_text
    assert "למעקב בלבד" in watch_text
    assert "0.0%" in watch_text
    assert "יציאה אוטומטית" not in watch_text
    assert "העתק את הפקודה" not in watch_text


def test_fmt_signed_pct_and_usd_helpers():
    from trading_pulse.telegram import telegram_format as tf

    assert "\u2212" in tf._fmt_signed_pct(-1.25)
    assert "+1.3%" in tf._fmt_signed_pct(1.26)
    assert "0.0%" in tf._fmt_signed_pct(0.0)
    assert "\u200e" in tf._fmt_signed_pct(-1.0)
    assert "<code>" in tf._fmt_usd(12.5)
    assert "\u2212$" in tf._fmt_usd(-3.2, signed=True)
    assert "+$3.20" in tf._fmt_usd(3.2, signed=True)
    assert "AAPL" in tf._fmt_ticker("aapl")
    assert "<b>" in tf._fmt_ticker("aapl")


def test_format_no_entries_morning():
    from trading_pulse.telegram.telegram_format import format_no_entries_morning

    text = format_no_entries_morning(trading_day="2026-07-15")
    assert "אין קניות היום" in text
    assert "2026-07-15" in text
    assert "התיק הקיים" in text


def test_format_plan_message_for_app_no_picks_matches_telegram():
    from trading_pulse.agent.dryrun_agent import format_plan_message_for_app

    plan = {
        "for_trading_day": "2026-07-15",
        "equity_snapshot": 1000,
        "available_capital_usd": 0,
        "deployed_capital_usd": 1000,
        "recommendations": [],
        "holdings": [
            {"symbol": "META", "capital_usd": 250, "entry_day": "2026-07-13", "days_held": 2},
        ],
        "holding_actions": [
            {
                "symbol": "META",
                "verdict": "hold",
                "pnl_pct": 2.0,
                "capital_usd": 250,
                "reason": "חזק",
            }
        ],
        "status": "no_picks",
        "scan_stats": {
            "tickers_scanned": 20,
            "before_quality": 2,
            "after_quality": 0,
            "min_entry_score": 7.0,
            "top_skipped_scores": [{"symbol": "AMD", "score": 6.5}],
        },
    }
    text = format_plan_message_for_app(plan)
    assert "אין המלצות היום" in text
    assert "איך לבצע" in text or "אין פעולה" in text
    assert "<b>" not in text
    assert "META" in text


def test_no_sell_on_mild_drop():
    cfg = FakeCfg()
    holdings = [{"symbol": "HOOD", "entry_price": 100.0}]
    quotes = {"HOOD": {"last": 96.0, "change_pct": -4.0}}
    alerts = {"HOOD": [PositionAlert("HOOD", "intraday_drop", "ירידה יומית", severity=2)]}
    suggestions = build_suggestions(cfg, holdings, {}, quotes, alerts)
    assert not any(s.kind == "sell" for s in suggestions)


def test_cooldown_filters_repeat_alerts():
    report = IntradayReport(
        checked_at="now",
        alerts=[PositionAlert("SOXL", "near_stop", "msg")],
        suggestions=[],
    )
    state = {
        "intraday_alert_cooldowns": {
            "SOXL:near_stop": datetime.now().isoformat(),
        }
    }
    filtered = filter_cooled_down(report, state, cooldown_minutes=120)
    assert filtered.alerts == []


def test_fetch_intraday_quote_returns_change_pct_and_day_change_pct():
    from trading_pulse.agent.intraday_monitor import fetch_intraday_quote

    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 106.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 105.0],
        }
    )
    with patch("trading_pulse.agent.intraday_monitor.yf.download", return_value=df):
        quote = fetch_intraday_quote("AAPL")
    assert quote is not None
    assert quote["last"] == 105.0
    assert quote["open"] == 100.0
    assert quote["change_pct"] == 5.0
    assert quote["day_change_pct"] == 5.0
    assert quote["change_pct"] == quote["day_change_pct"]


def test_plan_sell_or_cooldown_symbols_from_same_day_exits():
    from trading_pulse.agent.intraday_monitor import _plan_sell_or_cooldown_symbols

    state = {
        "history": [{"symbol": "path", "exit_day": "2026-07-21"}],
        "intraday_floor_exits": [{"symbol": "SOXL", "day": "2026-07-21"}],
        "symbol_cooldowns": {},
    }
    with (
        patch(
            "trading_pulse.agent.plan_engine.active_trading_day",
            return_value=None,
        ),
        patch(
            "trading_pulse.core.schedule_tz.us_trading_session_date",
            return_value=date(2026, 7, 21),
        ),
        patch(
            "trading_pulse.agent.symbol_cooldown.symbols_in_cooldown",
            return_value=set(),
        ),
    ):
        skip = _plan_sell_or_cooldown_symbols(FakeCfg(), state)
    assert "PATH" in skip
    assert "SOXL" in skip


def test_plan_sell_or_cooldown_symbols_from_plan_holding_actions(tmp_path):
    from trading_pulse.agent.dryrun_agent import save_json
    from trading_pulse.agent.intraday_monitor import _plan_sell_or_cooldown_symbols

    plan_file = tmp_path / "plan.json"
    save_json(
        plan_file,
        {
            "holding_actions": [
                {"symbol": "LABD", "verdict": "sell"},
                {"symbol": "RIVN", "verdict": "swap", "swap_to": "NVDA"},
                {"symbol": "META", "verdict": "hold"},
            ]
        },
    )
    with (
        patch(
            "trading_pulse.agent.plan_engine.active_trading_day",
            return_value="2026-07-21",
        ),
        patch(
            "trading_pulse.agent.dryrun_agent.plan_path",
            return_value=plan_file,
        ),
    ):
        skip = _plan_sell_or_cooldown_symbols(FakeCfg(), None)
    assert "LABD" in skip
    assert "RIVN" in skip
    assert "META" not in skip


def test_build_suggestions_skips_plan_sell_or_cooldown_symbols():
    cfg = FakeCfg(max_open_positions=4)
    holdings: list[dict] = []
    scores = {
        "LABU": {"score": 14.0, "ret_5d_pct": 8.0, "vol_ratio": 1.5, "volume_ok": True},
        "NVDA": {"score": 12.0, "ret_5d_pct": 5.0, "vol_ratio": 1.2, "volume_ok": True},
    }
    with patch(
        "trading_pulse.agent.intraday_monitor._plan_sell_or_cooldown_symbols",
        return_value={"LABU"},
    ):
        suggestions = build_suggestions(
            cfg, holdings, scores, {}, {}, state={"open_positions": []}
        )
    assert len(suggestions) == 1
    assert suggestions[0].kind == "buy"
    assert suggestions[0].symbol == "NVDA"


def test_append_idle_cash_topup_noop_without_holdings():
    from trading_pulse.agent.intraday_monitor import _append_idle_cash_topup

    suggestions: list = []
    _append_idle_cash_topup(
        FakeCfg(), [], {}, {"equity": 1000, "open_positions": []}, set(), suggestions
    )
    assert suggestions == []


def test_append_idle_cash_topup_noop_when_cash_too_low():
    from trading_pulse.agent.intraday_monitor import _append_idle_cash_topup

    holdings = [{"symbol": "AMD", "capital_usd": 990, "entry_price": 100}]
    state = {"equity": 1000, "open_positions": holdings}  # available cash = $10
    suggestions: list = []
    _append_idle_cash_topup(FakeCfg(), holdings, {}, state, set(), suggestions)
    assert suggestions == []


def test_append_idle_cash_topup_respects_custom_min_cash():
    from trading_pulse.agent.intraday_monitor import _append_idle_cash_topup

    cfg = FakeCfg(intraday_cash_topup_min_usd=500.0)
    holdings = [{"symbol": "AMD", "capital_usd": 700, "entry_price": 100}]
    state = {"equity": 1000, "open_positions": holdings}  # available cash = $300
    suggestions: list = []
    _append_idle_cash_topup(cfg, holdings, {}, state, set(), suggestions)
    assert suggestions == []  # below the custom $500 floor


def test_append_idle_cash_topup_noop_when_all_holdings_excluded():
    from trading_pulse.agent.intraday_monitor import _append_idle_cash_topup

    holdings = [{"symbol": "AMD", "capital_usd": 300, "entry_price": 100}]
    state = {"equity": 1000, "open_positions": holdings}  # available cash = $700
    suggestions: list = []
    _append_idle_cash_topup(FakeCfg(), holdings, {}, state, {"AMD"}, suggestions)
    assert suggestions == []


def test_append_idle_cash_topup_picks_best_scoring_holding():
    from trading_pulse.agent.intraday_monitor import _append_idle_cash_topup

    holdings = [
        {"symbol": "AMD", "capital_usd": 300, "entry_price": 100},
        {"symbol": "NVDA", "capital_usd": 300, "entry_price": 200},
    ]
    state = {"equity": 1000, "open_positions": holdings}  # available cash = $400
    scores = {"AMD": {"score": 8.0}, "NVDA": {"score": 14.0}}
    suggestions: list = []
    _append_idle_cash_topup(FakeCfg(), holdings, scores, state, set(), suggestions)
    assert len(suggestions) == 1
    assert suggestions[0].kind == "buy"
    assert suggestions[0].symbol == "NVDA"
    assert "$400" in suggestions[0].message
    assert "אין מקום לפוזיציה חדשה" in suggestions[0].message


def test_append_idle_cash_topup_uses_default_state_when_none():
    """`state=None` falls back to a zero-equity stand-in — should stay quiet."""
    from trading_pulse.agent.intraday_monitor import _append_idle_cash_topup

    holdings = [{"symbol": "AMD", "capital_usd": 0}]
    suggestions: list = []
    _append_idle_cash_topup(FakeCfg(), holdings, {}, None, set(), suggestions)
    assert suggestions == []


def test_build_suggestions_idle_cash_topup_fires_even_with_no_scores():
    """Idle-cash top-up must fire when full, even with zero new-buy candidates."""
    cfg = FakeCfg(max_open_positions=1)
    holdings = [{"symbol": "AMD", "entry_price": 100, "capital_usd": 300}]
    state = {"equity": 1000, "open_positions": holdings}
    suggestions = build_suggestions(cfg, holdings, {}, {}, {}, state=state)
    assert len(suggestions) == 1
    assert suggestions[0].kind == "buy"
    assert suggestions[0].symbol == "AMD"


def test_build_suggestions_idle_cash_topup_excludes_sell_flagged_holding():
    cfg = FakeCfg(max_open_positions=1)
    holdings = [{"symbol": "SOXL", "entry_price": 197.0, "capital_usd": 300}]
    quotes = {"SOXL": {"last": 168.0, "change_pct": -14.0}}
    alerts = {"SOXL": [PositionAlert("SOXL", "heavy_loss", "x", severity=2)]}
    state = {"equity": 1000, "open_positions": holdings}
    suggestions = build_suggestions(cfg, holdings, {}, quotes, alerts, state=state)
    # SOXL is flagged for sell — the idle-cash top-up must not target it too.
    assert not any(s.kind == "buy" for s in suggestions)


def test_build_suggestions_idle_cash_topup_alongside_new_buy_candidate():
    cfg = FakeCfg(max_open_positions=1)
    holdings = [{"symbol": "AMD", "entry_price": 100, "capital_usd": 300}]
    state = {"equity": 1000, "open_positions": holdings}
    scores = {
        "AMD": {"score": 8.0, "ret_5d_pct": 1.0, "vol_ratio": 1.0, "volume_ok": True},
        "NVDA": {"score": 8.5, "ret_5d_pct": 2.0, "vol_ratio": 1.1, "volume_ok": True},
    }
    suggestions = build_suggestions(cfg, holdings, scores, {}, {}, state=state)
    kinds = {(s.kind, s.symbol) for s in suggestions}
    # Book is full (no open slots) so no new-buy suggestion for NVDA is added —
    # only the idle-cash top-up for the existing holding (score gap too small
    # for a swap/watch suggestion to also fire).
    assert kinds == {("buy", "AMD")}


def test_agent_config_default_intraday_cash_topup_min_usd():
    from trading_pulse.agent.dryrun_agent import AgentConfig

    assert AgentConfig().intraday_cash_topup_min_usd == 20.0


def test_card_intraday_monitor_png_has_holding_squares():
    from trading_pulse.agent.intraday_monitor import TradeSuggestion
    from trading_pulse.telegram.reply_cards import card_intraday_monitor

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
        floor_sells=[
            {"symbol": "LCID", "exit_price": 6.35, "floor_price": 6.48, "pnl_usd": -11.85}
        ],
        suggestions=[TradeSuggestion(kind="sell", symbol="VLO", message="למכור")],
    )
    png = card_intraday_monitor(report)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 2000


def _noteworthy_report() -> IntradayReport:
    from trading_pulse.agent.intraday_monitor import TradeSuggestion

    return IntradayReport(
        checked_at="now",
        suggestions=[TradeSuggestion(kind="sell", symbol="VLO", message="למכור")],
    )


def test_run_intraday_check_sends_png_photo(tmp_path):
    from trading_pulse.agent.intraday_monitor import run_intraday_check

    cfg = FakeCfg()
    state: dict = {}
    photo_calls: list[dict] = []
    notify_calls: list = []

    def fake_photo(cfg_arg, img, caption, **kwargs):
        photo_calls.append(
            {"caption": caption, "img": img, "context": kwargs.get("context"), "inbox": kwargs.get("inbox_text")}
        )
        return True

    with (
        patch("trading_pulse.agent.dryrun_agent.is_us_trading_day", return_value=True),
        patch("trading_pulse.core.schedule_tz.us_trading_session_date", return_value=date(2026, 7, 23)),
        patch("trading_pulse.agent.intraday_monitor.is_within_market_hours", return_value=True),
        patch(
            "trading_pulse.agent.intraday_monitor.build_intraday_report",
            return_value=_noteworthy_report(),
        ),
        patch("trading_pulse.agent.intraday_monitor.filter_cooled_down", side_effect=lambda r, *a, **k: r),
        patch(
            "trading_pulse.telegram.reply_cards.card_intraday_monitor",
            return_value=b"\x89PNG\r\n\x1a\nfake",
        ),
        patch("trading_pulse.agent.dryrun_agent.send_telegram_photo", side_effect=fake_photo),
        patch("trading_pulse.agent.dryrun_agent.send_user_notification", side_effect=lambda *a, **k: notify_calls.append(a) or True),
        patch("trading_pulse.agent.dryrun_agent.plan_path", return_value=tmp_path / "missing.json"),
        patch("trading_pulse.agent.dryrun_agent.save_json"),
        patch("trading_pulse.agent.intraday_monitor.mark_cooldowns") as mark_cd,
    ):
        assert run_intraday_check(cfg, state) is True

    assert len(photo_calls) == 1
    assert photo_calls[0]["caption"] == "מעקב שעתי"
    assert photo_calls[0]["context"] == "intraday"
    assert photo_calls[0]["img"][:8] == b"\x89PNG\r\n\x1a\n"
    assert notify_calls == []
    mark_cd.assert_called_once()


def test_run_intraday_check_falls_back_to_html_when_card_fails(tmp_path):
    from trading_pulse.agent.intraday_monitor import run_intraday_check

    cfg = FakeCfg()
    state: dict = {}
    notify_calls: list[dict] = []

    def fake_notify(cfg_arg, text, **kwargs):
        notify_calls.append({"text": text, "context": kwargs.get("context"), "parse_mode": kwargs.get("parse_mode")})
        return True

    with (
        patch("trading_pulse.agent.dryrun_agent.is_us_trading_day", return_value=True),
        patch("trading_pulse.core.schedule_tz.us_trading_session_date", return_value=date(2026, 7, 23)),
        patch("trading_pulse.agent.intraday_monitor.is_within_market_hours", return_value=True),
        patch(
            "trading_pulse.agent.intraday_monitor.build_intraday_report",
            return_value=_noteworthy_report(),
        ),
        patch("trading_pulse.agent.intraday_monitor.filter_cooled_down", side_effect=lambda r, *a, **k: r),
        patch(
            "trading_pulse.telegram.reply_cards.card_intraday_monitor",
            side_effect=RuntimeError("pillow boom"),
        ),
        patch("trading_pulse.agent.dryrun_agent.send_telegram_photo", return_value=True),
        patch("trading_pulse.agent.dryrun_agent.send_user_notification", side_effect=fake_notify),
        patch("trading_pulse.agent.dryrun_agent.plan_path", return_value=tmp_path / "missing.json"),
        patch("trading_pulse.agent.dryrun_agent.save_json"),
        patch("trading_pulse.agent.intraday_monitor.mark_cooldowns"),
    ):
        assert run_intraday_check(cfg, state) is True

    assert len(notify_calls) == 1
    assert notify_calls[0]["context"] == "intraday"
    assert notify_calls[0]["parse_mode"] == "HTML"
    assert "VLO" in notify_calls[0]["text"] or "מעקב" in notify_calls[0]["text"]
