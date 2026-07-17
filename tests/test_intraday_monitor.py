"""Tests for intraday market monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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


def test_sell_recommended_on_near_stop_without_scores():
    cfg = FakeCfg()
    holdings = [{"symbol": "MSTR", "entry_price": 100.0}]
    quotes = {"MSTR": {"last": 89.0, "change_pct": -5.0}}
    alerts = {"MSTR": [PositionAlert("MSTR", "near_stop", "קרוב לרף", severity=3)]}
    suggestions = build_suggestions(cfg, holdings, {}, quotes, alerts)
    sells = [s for s in suggestions if s.kind == "sell" and s.symbol == "MSTR"]
    assert len(sells) == 1
    assert "קרוב לרף" in sells[0].message
    assert "ירידה חדה" not in sells[0].message


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
    assert "$333" in swaps[0].message


def test_sell_recommendation_holds_cash_when_no_candidate():
    cfg = FakeCfg()
    holdings = [{"symbol": "SOXL", "entry_price": 197.0}]
    quotes = {"SOXL": {"last": 168.0, "change_pct": -14.0}}
    alerts = {"SOXL": [PositionAlert("SOXL", "heavy_loss", "x", severity=2)]}
    suggestions = build_suggestions(cfg, holdings, {}, quotes, alerts)
    sells = [s for s in suggestions if s.kind == "sell"]
    assert len(sells) == 1
    assert "מזומן" in sells[0].message


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
