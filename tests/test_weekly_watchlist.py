"""Tests for the weekly watchlist funnel selection logic."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from trading_pulse.agent.weekly_watchlist import (
    W_ATR,
    W_SCORE,
    W_STRAT,
    W_VOL,
    _analyze_symbol_strategies,
    _normalize_ohlc,
    enabled_weekly_strategies,
    enrich_rows_with_strategies,
    rank_candidates,
    week_key,
)


def test_week_key_format():
    assert week_key(date(2026, 7, 7)) == "2026-W28"


def test_rank_prefers_high_score():
    rows = [
        {"symbol": "AAA", "score": 9.0, "atr_pct": 5.0, "vol_ratio": 1.5},
        {"symbol": "BBB", "score": 3.0, "atr_pct": 5.0, "vol_ratio": 1.5},
    ]
    ranked = rank_candidates(rows, target_size=2, use_strategy=False)
    assert ranked[0]["symbol"] == "AAA"


def test_rank_limits_to_target_size():
    rows = [
        {"symbol": f"S{i}", "score": float(i), "atr_pct": 4.0, "vol_ratio": 1.0}
        for i in range(10)
    ]
    ranked = rank_candidates(rows, target_size=3, use_strategy=False)
    assert len(ranked) == 3
    # highest scores kept
    assert {r["symbol"] for r in ranked} == {"S9", "S8", "S7"}


def test_rank_blends_volatility_and_volume():
    # Same score; higher ATR + volume should win.
    rows = [
        {"symbol": "CALM", "score": 7.0, "atr_pct": 2.0, "vol_ratio": 0.5},
        {"symbol": "WILD", "score": 7.0, "atr_pct": 12.0, "vol_ratio": 2.5},
    ]
    ranked = rank_candidates(rows, target_size=2, use_strategy=False)
    assert ranked[0]["symbol"] == "WILD"


def test_rank_handles_empty():
    assert rank_candidates([], target_size=5) == []


def test_rank_drops_blank_symbols_and_uppercases():
    rows = [
        {"symbol": "  ", "score": 99.0, "atr_pct": 9.0, "vol_ratio": 3.0},
        {"symbol": "aaa", "score": 5.0, "atr_pct": 4.0, "vol_ratio": 1.0},
    ]
    ranked = rank_candidates(rows, target_size=5, use_strategy=False)
    assert len(ranked) == 1
    assert ranked[0]["symbol"] == "AAA"


def test_rank_target_size_zero_keeps_at_least_one():
    rows = [{"symbol": "AAA", "score": 5.0, "atr_pct": 4.0, "vol_ratio": 1.0}]
    ranked = rank_candidates(rows, target_size=0, use_strategy=False)
    assert len(ranked) == 1


def test_rank_serializes_expected_keys():
    rows = [{"symbol": "AAA", "score": 8.0, "atr_pct": 6.0, "vol_ratio": 1.2}]
    ranked = rank_candidates(rows, target_size=1, use_strategy=False)
    assert set(ranked[0]) == {
        "symbol",
        "score",
        "atr_pct",
        "vol_ratio",
        "strategy_score",
        "strategy_hits",
        "strategy_ids",
        "composite",
    }


def test_rank_prefers_strategy_hits_when_enabled():
    # Equal base metrics so W_STRAT can decide (large score gaps outweigh strategy).
    rows = [
        {
            "symbol": "PLAIN",
            "score": 8.0,
            "atr_pct": 5.0,
            "vol_ratio": 1.5,
            "strategy_score": 0.0,
            "strategy_hits": 0,
            "strategy_ids": [],
        },
        {
            "symbol": "SETUP",
            "score": 8.0,
            "atr_pct": 5.0,
            "vol_ratio": 1.5,
            "strategy_score": 2.5,
            "strategy_hits": 2,
            "strategy_ids": ["rising_three", "method2"],
        },
    ]
    ranked = rank_candidates(rows, target_size=2, use_strategy=True)
    assert ranked[0]["symbol"] == "SETUP"
    assert ranked[0]["strategy_hits"] == 2
    assert ranked[0]["strategy_ids"] == ["rising_three", "method2"]
    assert ranked[0]["composite"] > ranked[1]["composite"]


def test_rank_ignores_strategy_when_use_strategy_false():
    rows = [
        {
            "symbol": "PLAIN",
            "score": 9.0,
            "atr_pct": 5.0,
            "vol_ratio": 1.5,
            "strategy_score": 0.0,
            "strategy_hits": 0,
            "strategy_ids": [],
        },
        {
            "symbol": "SETUP",
            "score": 7.0,
            "atr_pct": 5.0,
            "vol_ratio": 1.5,
            "strategy_score": 5.0,
            "strategy_hits": 3,
            "strategy_ids": ["method2"],
        },
    ]
    ranked = rank_candidates(rows, target_size=2, use_strategy=False)
    assert ranked[0]["symbol"] == "PLAIN"


def test_rank_falls_back_when_all_strategy_scores_zero():
    """No positive strategy signals → renormalize to score/atr/vol only."""
    rows = [
        {
            "symbol": "HIGH",
            "score": 9.0,
            "atr_pct": 5.0,
            "vol_ratio": 1.5,
            "strategy_score": 0.0,
        },
        {
            "symbol": "LOW",
            "score": 3.0,
            "atr_pct": 5.0,
            "vol_ratio": 1.5,
            "strategy_score": 0.0,
        },
    ]
    with_flag = rank_candidates(rows, target_size=2, use_strategy=True)
    without = rank_candidates(rows, target_size=2, use_strategy=False)
    assert with_flag[0]["symbol"] == without[0]["symbol"] == "HIGH"
    # Weights renormalize to sum ~1 without W_STRAT.
    base = W_SCORE + W_ATR + W_VOL
    assert with_flag[0]["composite"] == pytest.approx(without[0]["composite"], abs=1e-4)
    assert W_STRAT > 0 and base + W_STRAT == pytest.approx(1.0)


def test_enabled_strategies_respect_mode_and_flags():
    balanced = SimpleNamespace(
        strategy_mode="balanced_mix",
        candle_fourth_enabled=True,
        method2_enabled=True,
        trend_pullback_enabled=False,
        vcp_breakout_enabled=True,
        relative_strength_enabled=False,
    )
    assert enabled_weekly_strategies(balanced) == {"rising_three", "method2", "vcp_breakout"}

    score_only = SimpleNamespace(
        strategy_mode="score_only",
        candle_fourth_enabled=True,
        method2_enabled=True,
    )
    assert enabled_weekly_strategies(score_only) == set()

    rising_only = SimpleNamespace(
        strategy_mode="rising_three_only",
        candle_fourth_enabled=True,
        method2_enabled=True,
    )
    assert enabled_weekly_strategies(rising_only) == {"rising_three"}


def test_enabled_strategies_method2_only_and_disabled_flags():
    method2_only = SimpleNamespace(
        strategy_mode="method2_only",
        method2_enabled=True,
        candle_fourth_enabled=True,
    )
    assert enabled_weekly_strategies(method2_only) == {"method2"}

    method2_off = SimpleNamespace(
        strategy_mode="method2_only",
        method2_enabled=False,
    )
    assert enabled_weekly_strategies(method2_off) == set()

    rising_off = SimpleNamespace(
        strategy_mode="rising_three_only",
        candle_fourth_enabled=False,
    )
    assert enabled_weekly_strategies(rising_off) == set()


def test_enabled_strategies_balanced_includes_experimental_when_on():
    cfg = SimpleNamespace(
        strategy_mode="balanced_mix",
        candle_fourth_enabled=True,
        method2_enabled=True,
        trend_pullback_enabled=True,
        vcp_breakout_enabled=True,
        relative_strength_enabled=True,
    )
    assert enabled_weekly_strategies(cfg) == {
        "rising_three",
        "method2",
        "trend_pullback",
        "vcp_breakout",
        "relative_strength",
    }


def test_source_universe_is_deduped_and_expanded():
    from trading_pulse.agent.universe import SOURCE_UNIVERSE

    assert len(SOURCE_UNIVERSE) >= 300
    assert len(SOURCE_UNIVERSE) == len(set(SOURCE_UNIVERSE))
    # Expect the expanded ~420 liquid universe.
    assert len(SOURCE_UNIVERSE) >= 400


def test_format_weekly_watchlist_mentions_successful_scan():
    from trading_pulse.telegram.telegram_format import format_weekly_watchlist

    html = format_weekly_watchlist(
        {
            "week": "2026-W30",
            "scanned": 120,
            "universe_size": 420,
            "selected": 60,
            "symbols": ["AAA", "BBB"],
            "strategies_used": ["rising_three", "method2"],
            "strategy_hit_symbols": 18,
        }
    )
    assert "נסרקו בהצלחה" in html
    assert "120" in html
    assert "420" in html
    assert "אותות אסטרטגיה" in html
    assert "Rising Three" in html
    assert "נרות סיניים 2" in html
    assert "18" in html
    assert "AAA" in html and "BBB" in html
    assert "דוגמאות לעריכת הרשימה" in html
    assert "09:00 ישראל" in html


def test_format_weekly_watchlist_omits_strategy_line_when_unused():
    from trading_pulse.telegram.telegram_format import format_weekly_watchlist

    html = format_weekly_watchlist(
        {
            "week": "2026-W30",
            "scanned": 50,
            "universe_size": 420,
            "selected": 10,
            "symbols": ["ZZZ"],
            "strategies_used": [],
            "strategy_hit_symbols": 0,
        }
    )
    assert "נסרקו בהצלחה" in html
    assert "שיטות שזוהו" not in html
    assert "מומנטום · תנודתיות · נפח" in html
    assert "אותות אסטרטגיה" not in html


def test_format_weekly_watchlist_shows_top10_and_more_count():
    from trading_pulse.telegram.telegram_format import format_weekly_watchlist

    symbols = [f"S{i:02d}" for i in range(60)]
    html = format_weekly_watchlist(
        {
            "week": "2026-W30",
            "scanned": 400,
            "universe_size": 420,
            "selected": 60,
            "symbols": symbols,
            "strategies_used": [],
        }
    )
    assert "Top 10 ברשימה" in html
    for sym in symbols[:10]:
        assert sym in html
    assert "S59" not in html
    assert "S10" not in html  # 11th ticker omitted from preview
    assert "ועוד 50" in html

    import pandas as pd

    short = pd.DataFrame(
        {
            "Open": [1.0] * 10,
            "High": [1.1] * 10,
            "Low": [0.9] * 10,
            "Close": [1.0] * 10,
            "Volume": [1_000_000] * 10,
        }
    )
    assert _normalize_ohlc(short) is None
    assert _normalize_ohlc(None) is None

    missing = pd.DataFrame({"Open": [1.0] * 30, "Close": [1.0] * 30})
    assert _normalize_ohlc(missing) is None


def test_normalize_ohlc_accepts_long_enough_frame():
    import pandas as pd

    n = 30
    df = pd.DataFrame(
        {
            "Open": [10.0] * n,
            "High": [11.0] * n,
            "Low": [9.0] * n,
            "Close": [10.5] * n,
            "Volume": [2_000_000] * n,
        }
    )
    out = _normalize_ohlc(df)
    assert out is not None
    assert len(out) == n


def test_enrich_returns_unchanged_when_no_strategies(monkeypatch):
    calls: list[list[str]] = []

    def _should_not_download(symbols, **_kwargs):
        calls.append(list(symbols))
        return {}

    monkeypatch.setattr(
        "trading_pulse.agent.weekly_watchlist._download_ohlc_batch",
        _should_not_download,
    )
    rows = [{"symbol": "AAA", "score": 5.0, "atr_pct": 4.0, "vol_ratio": 1.0}]
    cfg = SimpleNamespace(strategy_mode="score_only")
    out = enrich_rows_with_strategies(rows, cfg)
    assert out == rows
    assert calls == []


def test_enrich_cap_zero_skips_download(monkeypatch):
    calls: list[list[str]] = []

    def _should_not_download(symbols, **_kwargs):
        calls.append(list(symbols))
        return {}

    monkeypatch.setattr(
        "trading_pulse.agent.weekly_watchlist._download_ohlc_batch",
        _should_not_download,
    )
    rows = [{"symbol": "AAA", "score": 5.0, "atr_pct": 4.0, "vol_ratio": 1.0}]
    cfg = SimpleNamespace(
        strategy_mode="balanced_mix",
        candle_fourth_enabled=True,
        method2_enabled=True,
        weekly_strategy_enrich_cap=0,
        weekly_scan_chunk=20,
        weekly_scan_throttle_sec=0,
    )
    out = enrich_rows_with_strategies(rows, cfg, strategies={"method2"}, enrich_cap=0)
    assert out == rows
    assert calls == []


def test_enrich_caps_to_top_scores_and_attaches_hits(monkeypatch):
    downloaded: list[list[str]] = []

    def fake_download(symbols, **_kwargs):
        downloaded.append([str(s).upper() for s in symbols])
        return {s: object() for s in symbols}

    def fake_analyze(symbol, ohlc, *, strategies, spy_ohlc, cfg):
        return 1.25, ["method2"]

    monkeypatch.setattr(
        "trading_pulse.agent.weekly_watchlist._download_ohlc_batch",
        fake_download,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.weekly_watchlist._analyze_symbol_strategies",
        fake_analyze,
    )

    rows = [
        {"symbol": "low", "score": 1.0, "atr_pct": 3.0, "vol_ratio": 0.8},
        {"symbol": "high", "score": 9.0, "atr_pct": 5.0, "vol_ratio": 1.5},
        {"symbol": "mid", "score": 5.0, "atr_pct": 4.0, "vol_ratio": 1.0},
    ]
    cfg = SimpleNamespace(
        weekly_scan_chunk=20,
        weekly_scan_throttle_sec=0,
        weekly_strategy_enrich_cap=150,
    )
    out = enrich_rows_with_strategies(
        rows, cfg, strategies={"method2"}, enrich_cap=2
    )
    by_sym = {r["symbol"].upper(): r for r in out}

    assert set(downloaded[0]) == {"HIGH", "MID"}
    assert by_sym["HIGH"]["strategy_hits"] == 1
    assert by_sym["HIGH"]["strategy_ids"] == ["method2"]
    assert by_sym["HIGH"]["strategy_score"] == 1.25
    assert by_sym["MID"]["strategy_hits"] == 1
    # Lowest base score was outside the enrich cap.
    assert by_sym["LOW"].get("strategy_hits", 0) == 0
    assert by_sym["LOW"].get("strategy_ids", []) == []


def test_analyze_symbol_strategies_adds_multi_hit_bonus(monkeypatch):
    monkeypatch.setattr(
        "trading_pulse.agent.candlestick_patterns.analyze_rising_three_methods",
        lambda _ohlc: {"full_match": True},
    )
    monkeypatch.setattr(
        "trading_pulse.agent.candle_method2.analyze_method2_daily",
        lambda *_a, **_k: {"side": "long"},
    )

    cfg = SimpleNamespace(min_avg_volume_20d=500_000, method2_allow_short=True)
    score, hits = _analyze_symbol_strategies(
        "AAA",
        object(),
        strategies={"rising_three", "method2"},
        spy_ohlc=None,
        cfg=cfg,
    )
    assert hits == ["rising_three", "method2"]
    # 1.25 + 1.25 + 0.5*(2-1) multi-hit bonus
    assert score == pytest.approx(3.0)


def test_analyze_partial_rising_three_gets_reduced_weight(monkeypatch):
    monkeypatch.setattr(
        "trading_pulse.agent.candlestick_patterns.analyze_rising_three_methods",
        lambda _ohlc: {"full_match": False},
    )
    cfg = SimpleNamespace()
    score, hits = _analyze_symbol_strategies(
        "AAA",
        object(),
        strategies={"rising_three"},
        spy_ohlc=None,
        cfg=cfg,
    )
    assert hits == ["rising_three"]
    # Analyzer rounds strategy score to 3 decimals (1.25 * 0.65 → 0.812).
    assert score == pytest.approx(0.812)
