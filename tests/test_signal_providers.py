"""Tests for Alpha Vantage / Finnhub / Alpaca signal fetchers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from trading_pulse.agent.signal_sources import (
    _ohlcv_df_from_series,
    _signal_from_ohlcv_df,
    fetch_alphavantage_signal,
    fetch_alpaca_signal,
    fetch_finnhub_signal,
)


def _sample_metrics_df() -> pd.DataFrame:
    closes = [100 + i * 0.5 for i in range(30)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    volumes = [1_000_000 + i * 10_000 for i in range(30)]
    return _ohlcv_df_from_series(closes=closes, highs=highs, lows=lows, volumes=volumes)


def test_signal_from_ohlcv_df_speculative():
    signal = _signal_from_ohlcv_df("finnhub", _sample_metrics_df(), True)
    assert signal is not None
    assert signal.source == "finnhub"
    assert signal.score > 0
    assert signal.ret_5d_pct is not None


@patch("trading_pulse.agent.signal_sources._env_key", return_value="test-key")
@patch("trading_pulse.agent.signal_sources.requests.get")
def test_fetch_finnhub_signal_parses_candles(mock_get, _mock_key):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "s": "ok",
            "c": [float(100 + i) for i in range(30)],
            "h": [float(101 + i) for i in range(30)],
            "l": [float(99 + i) for i in range(30)],
            "v": [float(1_000_000 + i * 1000) for i in range(30)],
            "t": list(range(30)),
        },
    )
    mock_get.return_value.raise_for_status = MagicMock()
    signal = fetch_finnhub_signal("LABU", True)
    assert signal is not None
    assert signal.source == "finnhub"
    assert signal.score > 0


@patch("trading_pulse.agent.signal_sources._env_key", return_value="test-key")
@patch("trading_pulse.agent.signal_sources.requests.get")
def test_fetch_alphavantage_signal_parses_daily(mock_get, _mock_key):
    series = {}
    for i in range(30):
        day = f"2026-05-{i + 1:02d}"
        price = 100 + i
        series[day] = {
            "1. open": str(price),
            "2. high": str(price + 1),
            "3. low": str(price - 1),
            "4. close": str(price + 0.5),
            "5. volume": str(1_000_000 + i * 1000),
        }
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"Time Series (Daily)": series},
    )
    mock_get.return_value.raise_for_status = MagicMock()
    signal = fetch_alphavantage_signal("LABU", True)
    assert signal is not None
    assert signal.source == "alphavantage"


@patch("trading_pulse.agent.signal_sources._env_key")
@patch("trading_pulse.agent.signal_sources.requests.get")
def test_fetch_alpaca_signal_requires_both_keys(mock_get, mock_env):
    mock_env.side_effect = lambda name: "id" if name == "ALPACA_API_KEY_ID" else ""
    assert fetch_alpaca_signal("LABU", True) is None
    mock_get.assert_not_called()


@patch("trading_pulse.agent.signal_sources._env_key")
@patch("trading_pulse.agent.signal_sources.requests.get")
def test_fetch_alpaca_signal_parses_bars(mock_get, mock_env):
    def _key(name: str) -> str:
        return "secret" if "SECRET" in name else "id"

    mock_env.side_effect = _key
    bars = [
        {"c": 100 + i, "h": 101 + i, "l": 99 + i, "v": 1_000_000 + i * 1000}
        for i in range(30)
    ]
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"bars": bars})
    mock_get.return_value.raise_for_status = MagicMock()
    signal = fetch_alpaca_signal("LABU", True)
    assert signal is not None
    assert signal.source == "alpaca"
