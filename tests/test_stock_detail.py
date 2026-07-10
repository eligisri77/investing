"""Tests for ad-hoc stock detail (מניה / ציון)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from trading_pulse.agent.dryrun_agent import parse_telegram_user_command
from trading_pulse.agent.signal_sources import SourceSignal
from trading_pulse.agent.stock_detail import analyze_symbol
from trading_pulse.telegram.reply_cards import card_stock_detail


def test_parse_stock_detail():
    assert parse_telegram_user_command("מניה NVDA") == {
        "kind": "stock_detail",
        "symbol": "NVDA",
    }
    assert parse_telegram_user_command("ציון aapl")["symbol"] == "AAPL"
    assert parse_telegram_user_command("score TSLA")["kind"] == "stock_detail"
    assert parse_telegram_user_command("ניתוח BEAM")["symbol"] == "BEAM"
    # RTL order from Hebrew Telegram keyboard
    assert parse_telegram_user_command("AAPL ציון") == {
        "kind": "stock_detail",
        "symbol": "AAPL",
    }
    assert parse_telegram_user_command("NVDA מניה")["symbol"] == "NVDA"


def test_card_stock_detail_watch_mode():
    from trading_pulse.telegram.reply_cards import card_stock_detail

    png = card_stock_detail(
        {
            "ok": True,
            "symbol": "AAPL",
            "on_watchlist": True,
            "would_pick": False,
            "speculative": True,
            "watch_mode": True,
            "watch_interval_min": 60,
            "live_quote": {"last": 313.81, "day_change_pct": 0.0, "high": 316.39, "low": 312.17},
            "gates": [],
            "rec": {
                "symbol": "AAPL",
                "score": 3.1,
                "score_technical": 3.0,
                "entry_ref_price": 313.0,
                "ret_5d_pct": 1.7,
                "vol_ratio": 0.17,
                "atr_pct": 2.8,
                "breakout_ok": False,
                "near_high_pct": -1.0,
                "stop_loss_price": 275.0,
                "take_profit_price": 390.0,
                "source_scores": {"yahoo": 3.1},
            },
        }
    )
    assert png.startswith(b"\x89PNG")


@patch("trading_pulse.agent.dryrun_agent.enrich_recommendations")
@patch("trading_pulse.agent.dryrun_agent.is_speculative", return_value=True)
@patch("trading_pulse.agent.ticker_manager.list_tickers", return_value=["RIVN"])
@patch("trading_pulse.agent.stock_detail.merge_source_signals")
@patch("trading_pulse.agent.stock_detail.fetch_all_source_signals")
def test_analyze_symbol_off_watchlist(mock_fetch, mock_merge, _mock_list, _mock_spec, mock_enrich):
    mock_fetch.return_value = [
        SourceSignal(
            source="yahoo",
            score=8.0,
            close=10.0,
            ret_5d=0.05,
            ret_5d_pct=5.0,
            vol_ratio=1.4,
            atr_pct=3.0,
            near_high_pct=-1.0,
            breakout_ok=True,
            volume_ok=True,
            above_ma20_pct=2.0,
            momentum_ok=True,
            extra={"avg_vol20": 2_000_000},
        )
    ]
    mock_merge.return_value = {
        "symbol": "NVDA",
        "close": 10.0,
        "ret_5d_pct": 5.0,
        "vol_ratio": 1.4,
        "atr_pct": 3.0,
        "near_high_pct": -1.0,
        "breakout_ok": True,
        "volume_ok": True,
        "above_ma20_pct": 2.0,
        "momentum_ok": True,
        "avg_vol20": 2_000_000,
        "score": 8.0,
        "score_technical": 8.0,
        "score_simple_avg": 8.0,
        "source_score_std": 0.0,
        "source_score_spread": 0.0,
        "source_disagreement": False,
        "source_scores": {"yahoo": 8.0},
        "sources_used": 1,
        "sources_list": ["Yahoo"],
    }
    cfg = SimpleNamespace(
        signal_sources=["yahoo"],
        min_signal_sources=1,
        min_price_usd=5.0,
        min_avg_volume_20d=500_000,
        min_volume_ratio=1.0,
        min_entry_score=7.0,
        stop_loss_pct=0.12,
        take_profit_pct=0.25,
        risk_profile="speculative",
        source_weights=None,
        max_source_score_std=4.5,
        max_source_score_spread=9.0,
        disagreement_score_penalty=0.75,
        exclude_on_source_disagreement=False,
        news_headlines_count=1,
        news_sources=[],
        sentiment_score_factor=1.0,
    )
    detail = analyze_symbol(cfg, "nvda")
    assert detail["ok"] is True
    assert detail["symbol"] == "NVDA"
    assert detail["on_watchlist"] is False
    assert detail["would_pick"] is True
    assert detail["rec"]["score"] == 8.0
    mock_enrich.assert_called_once()
