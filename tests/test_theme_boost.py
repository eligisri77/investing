"""Tests for quantum / data-center theme score bonus."""

from __future__ import annotations

from trading_pulse.agent.dryrun_agent import (
    format_enrichment_lines,
    format_rec_signal_compact,
)
from trading_pulse.agent.signal_sources import SourceSignal, merge_source_signals
from trading_pulse.agent.theme_boost import (
    THEME_SCORE_BONUS,
    theme_label_line,
    theme_score_bonus,
    theme_tags,
)


def test_quantum_symbol_gets_bonus_and_tag():
    assert theme_tags("IONQ") == ["quantum"]
    assert theme_score_bonus("ionq") == THEME_SCORE_BONUS
    assert "קוונטים" in theme_label_line("IONQ")


def test_datacenter_symbol_gets_bonus_and_tag():
    assert theme_tags("SMCI") == ["datacenter"]
    assert theme_score_bonus("SMCI") == THEME_SCORE_BONUS
    assert "Data center" in theme_label_line("SMCI")


def test_unlisted_symbol_no_bonus():
    assert theme_tags("AAPL") == []
    assert theme_score_bonus("AAPL") == 0.0
    assert theme_label_line("AAPL") == ""


def test_nvda_not_in_theme_lists():
    assert theme_score_bonus("NVDA") == 0.0


def _sig(source: str, score: float) -> SourceSignal:
    return SourceSignal(
        source=source,
        score=score,
        close=100.0,
        ret_5d=0.02,
        ret_5d_pct=2.0,
        momentum_ok=True,
        volume_ok=True,
    )


def test_merge_source_signals_adds_theme_bonus_for_ionq():
    merged = merge_source_signals(
        "IONQ",
        [_sig("yahoo", 10.0), _sig("nasdaq", 10.0)],
    )
    assert merged is not None
    assert merged["theme_tags"] == ["quantum"]
    assert merged["theme_score_bonus"] == THEME_SCORE_BONUS
    assert merged["score"] == merged["score_technical"] + THEME_SCORE_BONUS


def test_merge_source_signals_no_theme_bonus_for_plain():
    merged = merge_source_signals(
        "AAPL",
        [_sig("yahoo", 10.0), _sig("nasdaq", 10.0)],
    )
    assert merged is not None
    assert merged["theme_tags"] == []
    assert merged["theme_score_bonus"] == 0.0
    assert merged["score"] == merged["score_technical"]


def test_format_enrichment_lines_shows_theme_and_bonus():
    lines = format_enrichment_lines(
        {
            "symbol": "IONQ",
            "theme_tags": ["quantum"],
            "theme_score_bonus": THEME_SCORE_BONUS,
            "score": 11.0,
        }
    )
    assert lines
    assert lines[0] == "נושא: קוונטים (+1.0)"


def test_format_enrichment_lines_empty_without_theme():
    assert format_enrichment_lines({"symbol": "AAPL", "score": 10.0}) == []


def test_format_enrichment_lines_theme_from_symbol_fallback():
    lines = format_enrichment_lines(
        {"symbol": "SMCI", "theme_score_bonus": THEME_SCORE_BONUS, "score": 10.0}
    )
    assert lines
    assert "נושא: Data center" in lines[0]
    assert "(+1.0)" in lines[0]


def test_format_rec_signal_compact_includes_theme_label():
    line = format_rec_signal_compact(
        {
            "symbol": "IONQ",
            "score": 12.0,
            "momentum_ok": True,
            "pullback_ok": True,
            "ret_5d_pct": 2.0,
            "theme_tags": ["quantum"],
        },
        speculative=True,
    )
    assert "נושא: קוונטים" in line
    assert "ציון 12.0" in line
