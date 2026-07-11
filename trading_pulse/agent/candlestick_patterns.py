"""Japanese candlestick pattern scanners (evening plan fourth pick)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

PATTERN_RISING_THREE = "rising_three_methods"
PATTERN_LABEL_HE = "נרות · Rising Three Methods"


@dataclass
class PatternHit:
    symbol: str
    pattern: str
    pattern_score: float
    pattern_weak: bool
    close: float
    reason_he: str
    details: dict[str, Any] = field(default_factory=dict)


def _series_col(df: pd.DataFrame, name: str) -> pd.Series:
    col = df[name]
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]
    return col.astype(float)


def fetch_daily_ohlc(symbol: str, *, period: str = "3mo") -> pd.DataFrame | None:
    try:
        df = yf.download(
            symbol,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as ex:
        logging.debug("OHLC download failed for %s: %s", symbol, ex)
        return None
    if df is None or df.empty or len(df) < 25:
        return None
    need = {"Open", "High", "Low", "Close", "Volume"}
    if not need.issubset(set(df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns)):
        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df = df.copy()
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    if not need.issubset(df.columns):
        return None
    return df.dropna(subset=["Open", "High", "Low", "Close"]).copy()


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    if len(close) < period + 1:
        return float(np.mean(high[-period:] - low[-period:])) if len(close) else 0.0
    prev_c = close[:-1]
    h = high[1:]
    l = low[1:]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    return float(np.mean(tr[-period:]))


def analyze_rising_three_methods(ohlc: pd.DataFrame) -> dict[str, Any] | None:
    """
    Score Rising Three Methods on the last 5 daily bars.

    Returns a dict with pattern_score / pattern_weak even for partial matches.
    """
    if ohlc is None or len(ohlc) < 25:
        return None

    o = _series_col(ohlc, "Open").to_numpy()
    h = _series_col(ohlc, "High").to_numpy()
    l = _series_col(ohlc, "Low").to_numpy()
    c = _series_col(ohlc, "Close").to_numpy()
    v = _series_col(ohlc, "Volume").to_numpy() if "Volume" in ohlc.columns else np.ones(len(c))

    i0, i1, i2, i3, i4 = -5, -4, -3, -2, -1
    atr = _atr(h, l, c)
    body0 = float(c[i0] - o[i0])
    range0 = float(h[i0] - l[i0]) or 1e-9
    body4 = float(c[i4] - o[i4])
    range4 = float(h[i4] - l[i4]) or 1e-9

    bull0 = body0 > 0
    long0 = (body0 / range0) >= 0.55
    meaningful0 = atr <= 0 or abs(body0) >= 0.45 * atr

    middles = (i1, i2, i3)
    contained = all(float(h[i]) <= float(h[i0]) + 1e-9 and float(l[i]) >= float(l[i0]) - 1e-9 for i in middles)
    small_middles = all(abs(float(c[i] - o[i])) <= abs(body0) * 0.75 + 1e-9 for i in middles)

    bull4 = body4 > 0
    long4 = (body4 / range4) >= 0.50
    new_high_close = float(c[i4]) > max(float(c[i0]), float(c[i1]), float(c[i2]), float(c[i3]))

    ma20 = float(np.mean(c[-20:]))
    above_ma20 = float(c[i4]) >= ma20
    avg_vol = float(np.mean(v[-21:-1])) if len(v) >= 21 else float(np.mean(v[:-1]) or 1.0)
    vol_boost = avg_vol > 0 and float(v[i4]) >= 1.1 * avg_vol

    score = 0.0
    if bull0:
        score += 1.5
    if long0:
        score += 1.5
    if meaningful0:
        score += 0.5
    if contained:
        score += 2.0
    if small_middles:
        score += 1.0
    if bull4:
        score += 1.5
    if long4:
        score += 1.0
    if new_high_close:
        score += 2.0
    if above_ma20:
        score += 1.0
    if vol_boost:
        score += 0.5

    full = bool(
        bull0
        and long0
        and meaningful0
        and contained
        and small_middles
        and bull4
        and long4
        and new_high_close
    )
    # Require at least a recognizable core before treating as a candidate.
    if score < 4.0:
        return None

    weak = not full
    if full:
        reason = f"{PATTERN_LABEL_HE} — תבנית מלאה"
    else:
        missing: list[str] = []
        if not contained:
            missing.append("נרות אמצע מחוץ לטווח")
        if not new_high_close:
            missing.append("בלי סגירת שיא")
        if not long0 or not bull0:
            missing.append("נר ראשון חלש")
        if not long4 or not bull4:
            missing.append("נר סיום חלש")
        reason = f"{PATTERN_LABEL_HE} (חלש)"
        if missing:
            reason += " · " + ", ".join(missing[:2])

    return {
        "pattern": PATTERN_RISING_THREE,
        "pattern_score": round(score, 2),
        "pattern_weak": weak,
        "close": round(float(c[i4]), 4),
        "reason_he": reason,
        "above_ma20": above_ma20,
        "vol_boost": vol_boost,
        "atr": round(atr, 4),
        "full_match": full,
    }


def scan_rising_three_methods(
    symbols: list[str],
    *,
    exclude: set[str] | None = None,
    allow_partial: bool = True,
) -> PatternHit | None:
    """Scan symbols; return best Rising Three Methods hit (full preferred, else best partial)."""
    exclude = {s.upper() for s in (exclude or set())}
    best: PatternHit | None = None
    for raw in symbols:
        symbol = str(raw).upper().strip()
        if not symbol or symbol in exclude:
            continue
        ohlc = fetch_daily_ohlc(symbol)
        if ohlc is None:
            continue
        analysis = analyze_rising_three_methods(ohlc)
        if analysis is None:
            continue
        if analysis["pattern_weak"] and not allow_partial:
            continue
        hit = PatternHit(
            symbol=symbol,
            pattern=str(analysis["pattern"]),
            pattern_score=float(analysis["pattern_score"]),
            pattern_weak=bool(analysis["pattern_weak"]),
            close=float(analysis["close"]),
            reason_he=str(analysis["reason_he"]),
            details=analysis,
        )
        if best is None:
            best = hit
            continue
        # Prefer full matches, then higher score.
        best_full = not best.pattern_weak
        hit_full = not hit.pattern_weak
        if hit_full and not best_full:
            best = hit
        elif hit_full == best_full and hit.pattern_score > best.pattern_score:
            best = hit
    return best
