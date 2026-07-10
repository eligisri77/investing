"""Ad-hoc stock analysis for Telegram — works for watchlist and off-list symbols."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from trading_pulse.agent.signal_sources import (
    fetch_all_source_signals,
    merge_source_signals,
)


def analyze_symbol(cfg: Any, symbol: str) -> dict[str, Any]:
    """Score one symbol and return decision metrics (even if filters would reject it)."""
    from trading_pulse.agent.dryrun_agent import enrich_recommendations, is_speculative
    from trading_pulse.agent.ticker_manager import list_tickers, normalize_symbol

    symbol = normalize_symbol(symbol)
    speculative = is_speculative(cfg)
    sources = list(getattr(cfg, "signal_sources", None) or ["yahoo"])
    min_sources = int(getattr(cfg, "min_signal_sources", 1) or 1)
    min_price = float(getattr(cfg, "min_price_usd", 0) or 0)
    min_avg_vol = float(getattr(cfg, "min_avg_volume_20d", 0) or 0)
    min_vol_ratio = float(getattr(cfg, "min_volume_ratio", 1.0) or 1.0)
    min_entry = float(getattr(cfg, "min_entry_score", 0) or 0)

    on_watchlist = symbol in {t.upper() for t in list_tickers()}
    signals = fetch_all_source_signals(symbol, sources, speculative)
    if not signals:
        return {
            "ok": False,
            "symbol": symbol,
            "on_watchlist": on_watchlist,
            "error": "לא התקבלו נתונים ממקורות האותות",
        }

    merged = merge_source_signals(
        symbol,
        signals,
        source_weights=getattr(cfg, "source_weights", None),
        max_source_score_std=float(getattr(cfg, "max_source_score_std", 4.5)),
        max_source_score_spread=float(getattr(cfg, "max_source_score_spread", 9.0)),
        disagreement_score_penalty=float(getattr(cfg, "disagreement_score_penalty", 0.75)),
        exclude_on_source_disagreement=False,
    )
    if merged is None:
        return {
            "ok": False,
            "symbol": symbol,
            "on_watchlist": on_watchlist,
            "error": "לא ניתן לאחד ציונים מהמקורות",
        }

    close = float(merged.get("close") or 0)
    vol_ratio = float(merged.get("vol_ratio") or 0)
    avg_vol20 = merged.get("avg_vol20")
    volume_ok = vol_ratio >= min_vol_ratio
    merged["volume_ok"] = volume_ok

    gates: list[tuple[str, bool, str]] = []
    sources_ok = len(signals) >= min_sources
    gates.append(
        (
            "מקורות",
            sources_ok,
            f"{len(signals)}/{min_sources}",
        )
    )
    price_ok = close >= min_price
    gates.append(("מחיר מינימום", price_ok, f"${close:.2f} (סף ${min_price:.0f})"))
    if avg_vol20 is not None:
        vol20_ok = float(avg_vol20) >= min_avg_vol
        gates.append(
            (
                "נפח ממוצע 20י",
                vol20_ok,
                f"{float(avg_vol20):,.0f} (סף {min_avg_vol:,.0f})",
            )
        )
    else:
        gates.append(("נפח ממוצע 20י", False, "אין נתון"))

    if speculative:
        breakout_ok = bool(merged.get("breakout_ok"))
        strategy_ok = volume_ok or breakout_ok
        gates.append(
            (
                "אסטרטגיה",
                strategy_ok,
                "נפח/פריצה" if strategy_ok else "אין נפח ואין פריצה",
            )
        )
    else:
        momentum_ok = bool(merged.get("momentum_ok"))
        strategy_ok = momentum_ok or volume_ok
        gates.append(
            (
                "אסטרטגיה",
                strategy_ok,
                "מומנטום/נפח" if strategy_ok else "מתחת MA20 ובלי נפח",
            )
        )

    score = float(merged.get("score") or 0)
    score_ok = score >= min_entry
    gates.append(("ציון כניסה", score_ok, f"{score:.1f} (סף {min_entry:.1f})"))
    would_pick = all(ok for _, ok, _ in gates)

    sl = float(getattr(cfg, "stop_loss_pct", 0.12))
    tp = float(getattr(cfg, "take_profit_pct", 0.25))
    entry = close if close > 0 else 1.0
    rec: dict[str, Any] = {
        "symbol": symbol,
        "side": "LONG",
        "capital_usd": 0.0,
        "entry_ref_price": round(entry, 4),
        "stop_loss_price": round(entry * (1 - sl), 4),
        "take_profit_price": round(entry * (1 + tp), 4),
        "floor_price": round(entry * (1 - sl), 4),
        "stop_loss_pct": sl,
        "take_profit_pct": tp,
        "score": round(score, 4),
        "score_technical": round(float(merged.get("score_technical", score)), 4),
        "score_simple_avg": round(float(merged.get("score_simple_avg", score)), 4),
        "source_score_std": round(float(merged.get("source_score_std", 0)), 4),
        "source_score_spread": round(float(merged.get("source_score_spread", 0)), 4),
        "source_disagreement": bool(merged.get("source_disagreement", False)),
        "ret_5d_pct": round(float(merged.get("ret_5d_pct", 0)), 2),
        "vol_ratio": round(vol_ratio, 2),
        "volume_ok": volume_ok,
        "source_scores": dict(merged.get("source_scores") or {}),
        "sources_used": int(merged.get("sources_used") or len(signals)),
        "sources_list": list(merged.get("sources_list") or []),
        "approved": False,
        "atr_pct": round(float(merged.get("atr_pct", 0)), 2),
        "near_high_pct": round(float(merged.get("near_high_pct", 0)), 2),
        "breakout_ok": bool(merged.get("breakout_ok", False)),
        "above_ma20_pct": round(float(merged.get("above_ma20_pct", 0)), 2),
        "momentum_ok": bool(merged.get("momentum_ok", False)),
        "avg_vol20": avg_vol20,
    }

    try:
        enrich_recommendations([rec], cfg, speculative=speculative)
    except Exception as ex:
        logging.warning("Stock detail enrich failed for %s: %s", symbol, ex)

    return {
        "ok": True,
        "symbol": symbol,
        "on_watchlist": on_watchlist,
        "would_pick": would_pick,
        "gates": gates,
        "speculative": speculative,
        "rec": rec,
        "trading_day": date.today().isoformat(),
    }
