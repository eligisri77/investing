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
    market_open_sim_time: str = "16:40"
    market_close_sim_time: str = "23:10"


def test_is_within_market_hours():
    cfg = FakeCfg()
    inside = datetime(2026, 6, 17, 18, 0)
    outside = datetime(2026, 6, 17, 10, 0)
    assert is_within_market_hours(cfg, now=inside) is True
    assert is_within_market_hours(cfg, now=outside) is False


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
