"""Manual sell/swap must not claim «אין פוזיציה» when only today's bar is missing."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd

import trading_pulse.agent.dryrun_agent as agent
from trading_pulse.agent.dryrun_agent import AgentConfig
from trading_pulse.agent.positions import fetch_day_ohlc, partial_sell_position


class _Cfg:
    commission_per_side_usd = 0.0
    stop_loss_pct = 0.12
    take_profit_pct = 0.25


def _ohlc_frame(days_closes: list[tuple[str, float]]) -> pd.DataFrame:
    idx = pd.to_datetime([d for d, _ in days_closes])
    closes = [c for _, c in days_closes]
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Close": closes,
            "Adj Close": closes,
            "Volume": [1_000_000] * len(closes),
        },
        index=idx,
    )


def _held_state(symbol: str = "DUOL", capital: float = 400.0) -> dict:
    return {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": symbol,
                "capital_usd": capital,
                "entry_price": 156.0,
                "side": "LONG",
                "lots": [{"capital_usd": capital, "entry_price": 156.0}],
            }
        ],
    }


def test_fetch_day_ohlc_lookback_uses_prior_session_when_today_empty():
    frame = _ohlc_frame([("2026-09-04", 50.0), ("2026-09-05", 51.0)])

    def _fake_download(*_a, **_k):
        return frame

    with patch("trading_pulse.agent.positions.yf.download", side_effect=_fake_download):
        # «Today» is Monday 09-07 — no bar yet; lookback should pick Fri 09-05.
        bar = fetch_day_ohlc("DUOL", date(2026, 9, 7), lookback_calendar_days=10)
    assert bar is not None
    assert bar["close"] == 51.0


def test_fetch_day_ohlc_empty_download_returns_none_even_with_lookback():
    empty = pd.DataFrame()
    with patch("trading_pulse.agent.positions.yf.download", return_value=empty):
        assert fetch_day_ohlc("GTLB", date(2026, 9, 7), lookback_calendar_days=10) is None


def test_partial_sell_premarket_uses_lookback_close():
    state = _held_state()
    frame = _ohlc_frame([("2026-09-04", 150.0)])

    with patch("trading_pulse.agent.positions.yf.download", return_value=frame):
        trade = partial_sell_position(
            _Cfg(), state, "DUOL", 1.0, trading_day=date(2026, 9, 7)
        )
    assert trade is not None
    assert trade["symbol"] == "DUOL"
    assert trade["exit_price"] == 150.0
    assert not any(p["symbol"] == "DUOL" for p in state["open_positions"])


def test_partial_sell_returns_none_when_held_but_no_bars():
    state = _held_state("GTLB")
    with patch(
        "trading_pulse.agent.positions.yf.download",
        return_value=pd.DataFrame(),
    ):
        trade = partial_sell_position(
            _Cfg(), state, "GTLB", 1.0, trading_day=date(2026, 9, 7)
        )
    assert trade is None
    assert any(p["symbol"] == "GTLB" for p in state["open_positions"])


def test_execute_sell_held_no_price_does_not_say_no_position(monkeypatch):
    state = _held_state("DUOL")
    monkeypatch.setattr(agent, "load_state", lambda _cfg: state)
    monkeypatch.setattr(
        "trading_pulse.agent.positions.partial_sell_position",
        lambda *_a, **_k: None,
    )

    reply = agent.execute_sell_command(AgentConfig(), "DUOL", fraction=1.0)
    assert "אין פוזיציה" not in reply
    assert "יש פוזיציה" in reply
    assert "אין מחיר זמין" in reply
    assert "DUOL" in reply


def test_execute_sell_usd_held_no_price_does_not_say_no_position(monkeypatch):
    state = _held_state("GTLB")
    monkeypatch.setattr(agent, "load_state", lambda _cfg: state)
    monkeypatch.setattr(
        "trading_pulse.agent.positions.partial_sell_usd",
        lambda *_a, **_k: None,
    )

    reply = agent.execute_sell_command(AgentConfig(), "GTLB", sell_usd=100.0)
    assert "אין פוזיציה" not in reply
    assert "יש פוזיציה" in reply
    assert "אין מחיר זמין" in reply


def test_execute_sell_true_missing_still_says_no_position(monkeypatch):
    monkeypatch.setattr(
        agent, "load_state", lambda _cfg: {"equity": 1000.0, "open_positions": []}
    )
    monkeypatch.setattr(
        "trading_pulse.agent.positions.partial_sell_position",
        lambda *_a, **_k: None,
    )

    reply = agent.execute_sell_command(AgentConfig(), "DUOL", fraction=1.0)
    assert "אין פוזיציה" in reply
    assert "יש פוזיציה" not in reply


def test_execute_swap_held_no_price_does_not_say_no_position(monkeypatch, tmp_path):
    state = _held_state("DUOL")
    day = "2026-09-07"
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    monkeypatch.setattr(agent, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(agent, "PLANS_DIR", plans_dir)
    monkeypatch.setattr(agent, "resolve_trading_day", lambda _d: day)
    monkeypatch.setattr(agent, "load_state", lambda _cfg: state)
    monkeypatch.setattr(
        "trading_pulse.agent.trading_flow.before_market_entry",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.positions.partial_sell_position",
        lambda *_a, **_k: None,
    )

    reply = agent.execute_swap_command(AgentConfig(), "DUOL", "HOOD")
    assert "אין פוזיציה" not in reply
    assert "יש פוזיציה" in reply
    assert "אין מחיר זמין" in reply
    assert "DUOL" in reply


def test_execute_swap_true_missing_still_says_no_position(monkeypatch, tmp_path):
    day = "2026-09-07"
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    monkeypatch.setattr(agent, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(agent, "PLANS_DIR", plans_dir)
    monkeypatch.setattr(agent, "resolve_trading_day", lambda _d: day)
    monkeypatch.setattr(
        agent,
        "load_state",
        lambda _cfg: {"equity": 1000.0, "open_positions": []},
    )
    monkeypatch.setattr(
        "trading_pulse.agent.trading_flow.before_market_entry",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.positions.partial_sell_position",
        lambda *_a, **_k: None,
    )

    reply = agent.execute_swap_command(AgentConfig(), "DUOL", "HOOD")
    assert "אין פוזיציה" in reply
    assert "יש פוזיציה" not in reply
