"""Weekly watchlist funnel.

Once a week (weekend) we slowly scan a large source universe, rank every symbol
by a blend of momentum score, volatility (ATR) and liquidity, and keep the top
~60 as the trading watchlist for the coming week. The daily plan then only scans
that shortlist. Throttled to avoid data-source rate limits.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Any

from trading_pulse.core.app_paths import CONFIG_FILE, WATCHLIST_DIR

# Ranking weights (composite = weighted sum of min-max normalized metrics).
W_SCORE = 0.60
W_ATR = 0.25
W_VOL = 0.15


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


def rank_candidates(
    rows: list[dict[str, Any]],
    target_size: int,
) -> list[dict[str, Any]]:
    """Rank scored rows and return the top `target_size` with a composite score.

    Each row should have: symbol, score, atr_pct, vol_ratio (missing -> 0).
    """
    clean = [r for r in rows if str(r.get("symbol", "")).strip()]
    if not clean:
        return []

    scores = _norm([float(r.get("score", 0) or 0) for r in clean])
    atrs = _norm([float(r.get("atr_pct", 0) or 0) for r in clean])
    vols = _norm([float(r.get("vol_ratio", 0) or 0) for r in clean])

    ranked: list[dict[str, Any]] = []
    for row, s_n, a_n, v_n in zip(clean, scores, atrs, vols):
        composite = W_SCORE * s_n + W_ATR * a_n + W_VOL * v_n
        ranked.append(
            {
                "symbol": str(row["symbol"]).upper(),
                "score": round(float(row.get("score", 0) or 0), 2),
                "atr_pct": round(float(row.get("atr_pct", 0) or 0), 2),
                "vol_ratio": round(float(row.get("vol_ratio", 0) or 0), 2),
                "composite": round(composite, 4),
            }
        )

    ranked.sort(key=lambda x: -x["composite"])
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
                    }
                )
        if start + chunk_size < total and throttle_sec > 0:
            time.sleep(throttle_sec)
    return rows


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

    wk = week_key(week)
    logging.info(
        "Building weekly watchlist %s: universe=%d target=%d chunk=%d throttle=%.1fs",
        wk, len(SOURCE_UNIVERSE), size, chunk_size, throttle_sec,
    )
    rows = _scan_universe_throttled(
        cfg, SOURCE_UNIVERSE, chunk_size=chunk_size, throttle_sec=throttle_sec
    )
    selected = rank_candidates(rows, size)
    symbols = [r["symbol"] for r in selected]

    WATCHLIST_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "week": wk,
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "universe_size": len(SOURCE_UNIVERSE),
        "scanned": len(rows),
        "target_size": size,
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
