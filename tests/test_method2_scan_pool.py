"""Tests for Method2 expanded scan pool (watchlist first, universe fill)."""

from __future__ import annotations

from trading_pulse.agent.candle_method2 import (
    STRATEGY_LABEL_HE,
    Method2Hit,
    build_method2_scan_pool,
)


def test_build_method2_scan_pool_priority_then_universe():
    priority = ["AAA", "BBB"]
    universe = ["BBB", "CCC", "DDD", "EEE"]
    pool = build_method2_scan_pool(
        priority=priority,
        universe=universe,
        exclude=set(),
        cap=4,
    )
    assert pool[:2] == ["AAA", "BBB"]
    assert "CCC" in pool
    assert len(pool) == 4
    # No duplicates even though BBB is in both lists
    assert pool.count("BBB") == 1


def test_build_method2_scan_pool_respects_exclude_and_cap():
    pool = build_method2_scan_pool(
        priority=["AAPL", "MSFT"],
        universe=["NVDA", "AMD", "INTC", "QCOM"],
        exclude={"MSFT", "AMD"},
        cap=3,
    )
    assert "MSFT" not in pool
    assert "AMD" not in pool
    assert pool[0] == "AAPL"
    assert len(pool) == 3


def test_build_method2_scan_pool_expands_beyond_watchlist():
    watch = [f"W{i}" for i in range(60)]
    universe = watch + [f"U{i}" for i in range(200)]
    pool = build_method2_scan_pool(
        priority=watch,
        universe=universe,
        exclude=set(),
        cap=200,
    )
    assert len(pool) == 200
    assert pool[:60] == watch
    assert any(s.startswith("U") for s in pool[60:])


def test_build_method2_scan_pool_cap_zero_and_empty_inputs():
    assert build_method2_scan_pool(priority=["A"], universe=["B"], cap=0) == []
    assert (
        build_method2_scan_pool(priority=[], universe=[], exclude=None, cap=10) == []
    )


def _patch_scan_hits(monkeypatch, scores: dict[str, float]) -> None:
    from trading_pulse.agent import candle_method2 as m2

    def fetch(symbol: str, **kwargs):
        return {"symbol": symbol}

    def analyze(daily, **kwargs):
        sym = daily["symbol"]
        score = scores.get(sym)
        if score is None:
            return None
        return {
            "trigger": "2-1-2",
            "entry_ref": 10.0,
            "stop_ref": 9.0,
            "close": 9.5,
            "side": "LONG",
            "pattern_score": score,
            "atr_pct": 2.0,
        }

    monkeypatch.setattr(m2, "fetch_daily_ohlc", fetch)
    monkeypatch.setattr(m2, "analyze_method2_daily", analyze)
    monkeypatch.setattr(m2, "_market_cap", lambda _s: 1_000_000_000)


def test_scan_method2_top_n_returns_list(monkeypatch):
    from trading_pulse.agent import candle_method2 as m2

    _patch_scan_hits(monkeypatch, {"AAA": 9.0, "BBB": 8.0, "CCC": 7.0})

    hits = m2.scan_method2(["CCC", "AAA", "BBB", "ZZZ"], top_n=2, equity=1000.0)
    assert isinstance(hits, list)
    assert all(isinstance(h, Method2Hit) for h in hits)
    assert len(hits) == 2
    assert hits[0].symbol == "AAA"
    assert hits[1].symbol == "BBB"
    assert STRATEGY_LABEL_HE in hits[0].reason_he


def test_scan_method2_default_top_n_is_list_of_one(monkeypatch):
    """Return type is always list[Method2Hit] (no longer Optional single hit)."""
    from trading_pulse.agent import candle_method2 as m2

    _patch_scan_hits(monkeypatch, {"AAA": 9.0, "BBB": 8.0})

    hits = m2.scan_method2(["AAA", "BBB"], equity=1000.0)
    assert isinstance(hits, list)
    assert len(hits) == 1
    assert hits[0].symbol == "AAA"


def test_scan_method2_empty_when_no_setups(monkeypatch):
    from trading_pulse.agent import candle_method2 as m2

    _patch_scan_hits(monkeypatch, {})

    hits = m2.scan_method2(["AAA", "BBB"], top_n=3, equity=1000.0)
    assert hits == []


def test_scan_method2_respects_exclude_and_fewer_than_top_n(monkeypatch):
    from trading_pulse.agent import candle_method2 as m2

    _patch_scan_hits(monkeypatch, {"AAA": 9.0, "BBB": 8.0, "CCC": 7.0})

    hits = m2.scan_method2(
        ["AAA", "BBB", "CCC"],
        exclude={"AAA"},
        top_n=5,
        equity=1000.0,
    )
    assert [h.symbol for h in hits] == ["BBB", "CCC"]
