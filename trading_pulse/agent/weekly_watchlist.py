"""Weekly watchlist funnel.

Once a week (weekend) we slowly scan a large source universe, rank every symbol
by a blend of momentum score, volatility (ATR), liquidity, and enabled strategy
setups, then keep the top ~60 as the trading watchlist for the coming week.
The daily plan then only scans that shortlist. Throttled to avoid data-source
rate limits.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Any

from trading_pulse.core.app_paths import CONFIG_FILE, WATCHLIST_DIR

# Ranking weights (composite = weighted sum of min-max normalized metrics).
W_SCORE = 0.45
W_ATR = 0.18
W_VOL = 0.12
W_STRAT = 0.25

# Per-strategy hit weights used before normalizing strategy_score.
_STRATEGY_HIT_WEIGHTS = {
    "rising_three": 1.25,
    "method2": 1.25,
    "trend_pullback": 1.0,
    "vcp_breakout": 1.25,
    "relative_strength": 1.0,
}


def week_key(d: date | None = None) -> str:
    d = d or date.today()
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _norm(values: list[float]) -> list[float]:
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def enabled_weekly_strategies(cfg: Any) -> set[str]:
    """Which strategy analyzers participate in weekly ranking."""
    mode = str(getattr(cfg, "strategy_mode", "balanced_mix") or "balanced_mix")
    if mode == "score_only":
        return set()
    if mode == "rising_three_only":
        return {"rising_three"} if bool(getattr(cfg, "candle_fourth_enabled", True)) else set()
    if mode == "method2_only":
        return {"method2"} if bool(getattr(cfg, "method2_enabled", True)) else set()

    out: set[str] = set()
    if bool(getattr(cfg, "candle_fourth_enabled", True)):
        out.add("rising_three")
    if bool(getattr(cfg, "method2_enabled", True)):
        out.add("method2")
    if bool(getattr(cfg, "trend_pullback_enabled", False)):
        out.add("trend_pullback")
    if bool(getattr(cfg, "vcp_breakout_enabled", False)):
        out.add("vcp_breakout")
    if bool(getattr(cfg, "relative_strength_enabled", False)):
        out.add("relative_strength")
    return out


def rank_candidates(
    rows: list[dict[str, Any]],
    target_size: int,
    *,
    use_strategy: bool = True,
) -> list[dict[str, Any]]:
    """Rank scored rows and return the top `target_size` with a composite score.

    Each row should have: symbol, score, atr_pct, vol_ratio (missing -> 0).
    Optional: strategy_score, strategy_hits, strategy_ids.
    """
    clean = [r for r in rows if str(r.get("symbol", "")).strip()]
    if not clean:
        return []

    scores = _norm([float(r.get("score", 0) or 0) for r in clean])
    atrs = _norm([float(r.get("atr_pct", 0) or 0) for r in clean])
    vols = _norm([float(r.get("vol_ratio", 0) or 0) for r in clean])
    strat_raw = [float(r.get("strategy_score", 0) or 0) for r in clean]
    strats = _norm(strat_raw) if use_strategy and any(v > 0 for v in strat_raw) else [0.0] * len(clean)

    w_score = W_SCORE
    w_atr = W_ATR
    w_vol = W_VOL
    w_strat = W_STRAT if use_strategy else 0.0
    if not use_strategy or not any(v > 0 for v in strat_raw):
        # Re-normalize weights when strategy signals are absent.
        base = w_score + w_atr + w_vol
        w_score, w_atr, w_vol, w_strat = w_score / base, w_atr / base, w_vol / base, 0.0

    ranked: list[dict[str, Any]] = []
    for row, s_n, a_n, v_n, st_n in zip(clean, scores, atrs, vols, strats):
        composite = w_score * s_n + w_atr * a_n + w_vol * v_n + w_strat * st_n
        hits = [str(x) for x in (row.get("strategy_ids") or []) if str(x).strip()]
        ranked.append(
            {
                "symbol": str(row["symbol"]).upper(),
                "score": round(float(row.get("score", 0) or 0), 2),
                "atr_pct": round(float(row.get("atr_pct", 0) or 0), 2),
                "vol_ratio": round(float(row.get("vol_ratio", 0) or 0), 2),
                "strategy_score": round(float(row.get("strategy_score", 0) or 0), 2),
                "strategy_hits": int(row.get("strategy_hits", len(hits)) or 0),
                "strategy_ids": hits,
                "composite": round(composite, 4),
            }
        )

    ranked.sort(key=lambda x: (-x["composite"], -x["strategy_score"], -x["score"]))
    return ranked[: max(1, int(target_size))]


def _scan_universe_throttled(
    cfg: Any,
    symbols: list[str],
    *,
    chunk_size: int,
    throttle_sec: float,
) -> list[dict[str, Any]]:
    from trading_pulse.agent.dryrun_agent import fetch_signal_universe

    rows: list[dict[str, Any]] = []
    total = len(symbols)
    for start in range(0, total, max(1, chunk_size)):
        chunk = symbols[start : start + chunk_size]
        logging.info(
            "Weekly scan: chunk %d-%d of %d", start + 1, min(start + chunk_size, total), total
        )
        try:
            df = fetch_signal_universe(chunk, cfg)
        except Exception as ex:  # keep going; partial data still useful
            logging.warning("Weekly scan chunk failed (%s): %s", chunk, ex)
            df = None
        if df is not None and not df.empty:
            for _, r in df.iterrows():
                rows.append(
                    {
                        "symbol": str(r["symbol"]),
                        "score": float(r.get("score", 0) or 0),
                        "atr_pct": float(r.get("atr_pct", 0) or 0),
                        "vol_ratio": float(r.get("vol_ratio", 0) or 0),
                        "strategy_score": 0.0,
                        "strategy_hits": 0,
                        "strategy_ids": [],
                    }
                )
        if start + chunk_size < total and throttle_sec > 0:
            time.sleep(throttle_sec)
    return rows


def _normalize_ohlc(df: Any) -> Any:
    import pandas as pd

    if df is None or getattr(df, "empty", True):
        return None
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [c[0] if isinstance(c, tuple) else c for c in out.columns]
    need = {"Open", "High", "Low", "Close", "Volume"}
    if not need.issubset(out.columns):
        return None
    cleaned = out.dropna(subset=["Open", "High", "Low", "Close"])
    return cleaned if len(cleaned) >= 25 else None


def _download_ohlc_batch(
    symbols: list[str],
    *,
    period: str = "1y",
    chunk_size: int = 25,
    throttle_sec: float = 1.0,
) -> dict[str, Any]:
    import pandas as pd
    import yfinance as yf

    frames: dict[str, Any] = {}
    total = len(symbols)
    for start in range(0, total, max(1, chunk_size)):
        chunk = [str(s).upper() for s in symbols[start : start + chunk_size]]
        logging.info(
            "Weekly strategy OHLC: chunk %d-%d of %d",
            start + 1,
            min(start + chunk_size, total),
            total,
        )
        try:
            raw = yf.download(
                chunk,
                period=period,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
                group_by="ticker",
            )
        except Exception as ex:
            logging.warning("Weekly OHLC batch failed (%s): %s", chunk, ex)
            raw = None

        if raw is None or raw.empty:
            pass
        elif len(chunk) == 1:
            norm = _normalize_ohlc(raw)
            if norm is not None:
                frames[chunk[0]] = norm
        elif isinstance(raw.columns, pd.MultiIndex):
            for sym in chunk:
                try:
                    piece = raw[sym]
                except Exception:
                    continue
                norm = _normalize_ohlc(piece)
                if norm is not None:
                    frames[sym] = norm

        if start + chunk_size < total and throttle_sec > 0:
            time.sleep(throttle_sec)
    return frames


def _analyze_symbol_strategies(
    symbol: str,
    ohlc: Any,
    *,
    strategies: set[str],
    spy_ohlc: Any,
    cfg: Any,
) -> tuple[float, list[str]]:
    hits: list[str] = []
    score = 0.0

    if "rising_three" in strategies:
        from trading_pulse.agent.candlestick_patterns import analyze_rising_three_methods

        try:
            hit = analyze_rising_three_methods(ohlc)
        except Exception:
            hit = None
        if hit:
            hits.append("rising_three")
            weight = _STRATEGY_HIT_WEIGHTS["rising_three"]
            if hit.get("full_match"):
                score += weight
            else:
                score += weight * 0.65

    if "method2" in strategies:
        from trading_pulse.agent.candle_method2 import analyze_method2_daily

        try:
            hit = analyze_method2_daily(
                ohlc,
                min_avg_volume=float(getattr(cfg, "min_avg_volume_20d", 500_000) or 500_000),
                allow_short=bool(getattr(cfg, "method2_allow_short", True)),
            )
        except Exception:
            hit = None
        if hit:
            hits.append("method2")
            score += _STRATEGY_HIT_WEIGHTS["method2"]

    if "trend_pullback" in strategies:
        from trading_pulse.agent.strategies.trend_pullback import analyze_trend_pullback

        try:
            hit = analyze_trend_pullback(
                ohlc,
                symbol=symbol,
                stop_loss_pct=float(getattr(cfg, "stop_loss_pct", 0.06) or 0.06),
                take_profit_pct=float(getattr(cfg, "take_profit_pct", 0.12) or 0.12),
            )
        except Exception:
            hit = None
        if hit is not None:
            hits.append("trend_pullback")
            score += _STRATEGY_HIT_WEIGHTS["trend_pullback"]

    if "vcp_breakout" in strategies:
        from trading_pulse.agent.strategies.vcp_breakout import analyze_vcp_breakout

        try:
            hit = analyze_vcp_breakout(
                ohlc,
                symbol=symbol,
                stop_loss_pct=float(getattr(cfg, "stop_loss_pct", 0.07) or 0.07),
                take_profit_pct=float(getattr(cfg, "take_profit_pct", 0.14) or 0.14),
                min_price_usd=float(getattr(cfg, "min_price_usd", 5.0) or 5.0),
                min_avg_volume_20d=float(getattr(cfg, "min_avg_volume_20d", 500_000) or 500_000),
            )
        except Exception:
            hit = None
        if hit is not None:
            hits.append("vcp_breakout")
            score += _STRATEGY_HIT_WEIGHTS["vcp_breakout"]

    if "relative_strength" in strategies and spy_ohlc is not None:
        from trading_pulse.agent.strategies.relative_strength import analyze_relative_strength

        try:
            hit = analyze_relative_strength(
                ohlc,
                spy_ohlc,
                symbol=symbol,
                stop_loss_pct=float(getattr(cfg, "stop_loss_pct", 0.08) or 0.08),
                take_profit_pct=float(getattr(cfg, "take_profit_pct", 0.16) or 0.16),
                min_price_usd=float(getattr(cfg, "min_price_usd", 5.0) or 5.0),
                min_avg_volume_20d=float(getattr(cfg, "min_avg_volume_20d", 500_000) or 500_000),
            )
        except Exception:
            hit = None
        if hit is not None:
            hits.append("relative_strength")
            score += _STRATEGY_HIT_WEIGHTS["relative_strength"]

    if len(hits) >= 2:
        score += 0.5 * (len(hits) - 1)
    return round(score, 3), hits


def enrich_rows_with_strategies(
    rows: list[dict[str, Any]],
    cfg: Any,
    *,
    strategies: set[str] | None = None,
    enrich_cap: int | None = None,
) -> list[dict[str, Any]]:
    """Attach strategy hits to already-scored weekly candidates.

    Only symbols that already passed the base scan are enriched, to limit
    download volume. Experimental strategies follow the same enable flags as
    the daily plan.
    """
    if not rows:
        return rows
    active = strategies if strategies is not None else enabled_weekly_strategies(cfg)
    if not active:
        return rows

    # Prefer enriching the strongest base-momentum names first when capped.
    ordered = sorted(
        rows,
        key=lambda r: (
            float(r.get("score", 0) or 0),
            float(r.get("atr_pct", 0) or 0),
            float(r.get("vol_ratio", 0) or 0),
        ),
        reverse=True,
    )
    cap = enrich_cap
    if cap is None:
        cap = int(getattr(cfg, "weekly_strategy_enrich_cap", 150) or 150)
    cap = max(0, int(cap))
    targets = ordered[:cap] if cap else []
    if not targets:
        return rows

    symbols = [str(r["symbol"]).upper() for r in targets]
    need_spy = "relative_strength" in active
    if need_spy and "SPY" not in symbols:
        download_syms = symbols + ["SPY"]
    else:
        download_syms = symbols

    chunk = int(getattr(cfg, "weekly_scan_chunk", 20) or 20)
    throttle = float(getattr(cfg, "weekly_scan_throttle_sec", 1.5) or 1.5)
    frames = _download_ohlc_batch(
        download_syms,
        period="1y",
        chunk_size=max(5, chunk),
        throttle_sec=max(0.0, throttle),
    )
    spy_ohlc = frames.get("SPY")

    by_symbol = {str(r["symbol"]).upper(): dict(r) for r in rows}
    enriched = 0
    for sym in symbols:
        ohlc = frames.get(sym)
        if ohlc is None:
            continue
        strat_score, hits = _analyze_symbol_strategies(
            sym,
            ohlc,
            strategies=active,
            spy_ohlc=spy_ohlc,
            cfg=cfg,
        )
        row = by_symbol.get(sym)
        if row is None:
            continue
        row["strategy_score"] = strat_score
        row["strategy_hits"] = len(hits)
        row["strategy_ids"] = hits
        by_symbol[sym] = row
        if hits:
            enriched += 1

    logging.info(
        "Weekly strategy enrich: analyzed=%d hits=%d strategies=%s",
        len(symbols),
        enriched,
        sorted(active),
    )
    return list(by_symbol.values())


def _update_config_tickers(symbols: list[str]) -> None:
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg_raw = json.load(f)
    cfg_raw["tickers"] = symbols
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(cfg_raw, f, indent=2, ensure_ascii=False)
        f.write("\n")


def build_weekly_watchlist(
    cfg: Any,
    *,
    target_size: int | None = None,
    week: date | None = None,
    update_config: bool = True,
) -> dict[str, Any]:
    """Scan the source universe, select the top symbols, persist, and (optionally)
    set them as the active watchlist in config.json."""
    from trading_pulse.agent.universe import SOURCE_UNIVERSE

    size = int(target_size or getattr(cfg, "weekly_watchlist_size", 60))
    chunk_size = int(getattr(cfg, "weekly_scan_chunk", 20))
    throttle_sec = float(getattr(cfg, "weekly_scan_throttle_sec", 1.5))
    strategy_rank = bool(getattr(cfg, "weekly_strategy_rank_enabled", True))
    strategies = enabled_weekly_strategies(cfg) if strategy_rank else set()

    wk = week_key(week)
    logging.info(
        "Building weekly watchlist %s: universe=%d target=%d chunk=%d throttle=%.1fs strategies=%s",
        wk,
        len(SOURCE_UNIVERSE),
        size,
        chunk_size,
        throttle_sec,
        sorted(strategies) if strategies else "off",
    )
    rows = _scan_universe_throttled(
        cfg, SOURCE_UNIVERSE, chunk_size=chunk_size, throttle_sec=throttle_sec
    )
    if strategies:
        rows = enrich_rows_with_strategies(rows, cfg, strategies=strategies)
    selected = rank_candidates(rows, size, use_strategy=bool(strategies))
    symbols = [r["symbol"] for r in selected]
    strategy_hit_symbols = sum(1 for r in selected if int(r.get("strategy_hits", 0) or 0) > 0)

    WATCHLIST_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "week": wk,
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "universe_size": len(SOURCE_UNIVERSE),
        "scanned": len(rows),
        "target_size": size,
        "strategies_used": sorted(strategies),
        "strategy_hit_symbols": strategy_hit_symbols,
        "symbols": selected,
    }
    out_path = WATCHLIST_DIR / f"weekly_{wk}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    logging.info("Weekly watchlist saved: %s (%d symbols)", out_path, len(symbols))

    if update_config and symbols:
        _update_config_tickers(symbols)
        logging.info("Config watchlist updated with %d symbols", len(symbols))

    return {
        "week": wk,
        "universe_size": len(SOURCE_UNIVERSE),
        "scanned": len(rows),
        "selected": len(symbols),
        "symbols": symbols,
        "strategies_used": sorted(strategies),
        "strategy_hit_symbols": strategy_hit_symbols,
        "path": str(out_path),
        "updated_config": bool(update_config and symbols),
    }


def latest_weekly_watchlist() -> dict[str, Any] | None:
    if not WATCHLIST_DIR.exists():
        return None
    files = sorted(WATCHLIST_DIR.glob("weekly_*.json"), reverse=True)
    if not files:
        return None
    with files[0].open("r", encoding="utf-8") as f:
        return json.load(f)
