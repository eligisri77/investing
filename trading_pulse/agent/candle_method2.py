"""Method 2 (שיטה 2): candle types 1/2/3 + multi-TF alignment + pending triggers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

STRATEGY_ID = "method2"
STRATEGY_LABEL_HE = "שיטה 2"

# Pending daily sequences → expected trigger name for tomorrow
PENDING_TO_TRIGGER: dict[tuple[int, ...], str] = {
    (2, 1): "2-1-2",
    (3, 1): "3-1-2",
    (3,): "3-2",
    (3, 2): "3-2-2",
    (2, 2): "2-2-2",
}


@dataclass
class Method2Hit:
    symbol: str
    trigger: str
    pattern_score: float
    close: float
    entry_ref: float
    stop_ref: float
    reason_he: str
    capital_usd: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


def _series_col(df: pd.DataFrame, name: str) -> pd.Series:
    col = df[name]
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]
    return col.astype(float)


def _flatten_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


def fetch_daily_ohlc(symbol: str, *, period: str = "2y") -> pd.DataFrame | None:
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
        logging.debug("Method2 OHLC failed %s: %s", symbol, ex)
        return None
    df = _flatten_ohlc(df)
    if df is None or df.empty or len(df) < 30:
        return None
    need = {"Open", "High", "Low", "Close"}
    if not need.issubset(df.columns):
        return None
    return df.dropna(subset=["Open", "High", "Low", "Close"]).copy()


def classify_bar(
    prev_high: float,
    prev_low: float,
    high: float,
    low: float,
) -> int:
    """1=inside, 2=one-sided break, 3=outside (took both sides)."""
    took_high = high > prev_high
    took_low = low < prev_low
    if took_high and took_low:
        return 3
    if took_high or took_low:
        return 2
    return 1


def classify_series(high: np.ndarray, low: np.ndarray) -> list[int]:
    out: list[int] = [0]
    for i in range(1, len(high)):
        out.append(classify_bar(float(high[i - 1]), float(low[i - 1]), float(high[i]), float(low[i])))
    return out


def _atr_pct(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    if len(close) < period + 1:
        return 0.0
    prev_c = close[:-1]
    h = high[1:]
    l = low[1:]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr = float(np.mean(tr[-period:]))
    last = float(close[-1]) or 1.0
    return atr / last * 100.0


def _bullish_bias_for_bar(
    o: float,
    h: float,
    l: float,
    c: float,
    prev_h: float,
    prev_l: float,
    kind: int,
) -> bool:
    """Long-only MVP: prefer upside breaks / closes."""
    if kind == 1:
        return c >= o
    if kind == 2:
        took_high = h > prev_h
        took_low = l < prev_l
        if took_high and not took_low:
            return True
        if took_low and not took_high:
            return False
        return c >= o
    # type 3 outside
    return c >= (h + l) / 2.0 or c >= o


def detect_pending_trigger(
    types: list[int],
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
) -> dict[str, Any] | None:
    """After today's close, find a pending setup for tomorrow (long-only)."""
    if len(types) < 3:
        return None

    for length in (2, 1):
        seq = tuple(types[-length:])
        trigger = PENDING_TO_TRIGGER.get(seq)
        if not trigger:
            continue

        # Bullish bias on the break bar(s) that started the pattern
        if length == 2:
            i_break, i_last = -2, -1
        else:
            i_break = i_last = -1

        prev_i = i_break - 1
        if abs(prev_i) > len(types):
            continue
        kind_break = types[i_break]
        if not _bullish_bias_for_bar(
            float(opens[i_break]),
            float(highs[i_break]),
            float(lows[i_break]),
            float(closes[i_break]),
            float(highs[prev_i]),
            float(lows[prev_i]),
            kind_break,
        ):
            continue

        entry_ref, stop_ref = _levels_for_pending(
            trigger, seq, opens, highs, lows, closes
        )
        if entry_ref is None or stop_ref is None or entry_ref <= stop_ref:
            continue

        return {
            "trigger": trigger,
            "pending_seq": list(seq),
            "entry_ref": round(float(entry_ref), 4),
            "stop_ref": round(float(stop_ref), 4),
            "close": round(float(closes[-1]), 4),
        }
    return None


def _levels_for_pending(
    trigger: str,
    seq: tuple[int, ...],
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
) -> tuple[float | None, float | None]:
    """Reference entry/stop from completed bars (cent buffers)."""
    cent = 0.01
    if trigger in {"2-1-2", "3-1-2"} and seq[-1] == 1:
        # Levels from the inside bar (1)
        return float(highs[-1]) + cent, float(lows[-1]) - cent
    if trigger == "3-2" and seq == (3,):
        return float(highs[-1]) + cent, float(opens[-1])
    if trigger == "3-2-2" and seq == (3, 2):
        # Entry above middle 2 (last bar); stop below its open
        return float(highs[-1]) + cent, float(opens[-1]) - cent
    if trigger == "2-2-2" and seq == (2, 2):
        # Entry above middle 2 (first of the two 2s = -2); stop below open of entry 2
        return float(highs[-2]) + cent, float(opens[-2]) - cent
    return None, None


def _resample_ohlc(daily: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
    }
    if "Volume" in daily.columns:
        agg["Volume"] = "sum"
    out = daily.resample(rule).agg(agg).dropna(subset=["Open", "High", "Low", "Close"])
    return out


def htf_allows_trade(daily: pd.DataFrame) -> tuple[bool, dict[str, Any]]:
    """Reject when weekly or monthly current bar is type 1 (inside/discovery)."""
    info: dict[str, Any] = {}
    if not isinstance(daily.index, pd.DatetimeIndex):
        daily = daily.copy()
        daily.index = pd.to_datetime(daily.index)

    frames = {
        "W": _resample_ohlc(daily, "W-FRI"),
        "M": _resample_ohlc(daily, "ME"),
    }
    # Quarterly / yearly from monthly
    monthly = frames["M"]
    if len(monthly) >= 4:
        frames["Q"] = _resample_ohlc(monthly, "QE")
    if len(monthly) >= 12:
        frames["Y"] = _resample_ohlc(monthly, "YE")

    for name, frame in frames.items():
        if frame is None or len(frame) < 2:
            info[name] = None
            continue
        h = _series_col(frame, "High").to_numpy()
        l = _series_col(frame, "Low").to_numpy()
        kind = classify_bar(float(h[-2]), float(l[-2]), float(h[-1]), float(l[-1]))
        info[name] = kind

    w = info.get("W")
    m = info.get("M")
    if w == 1 or m == 1:
        return False, info
    return True, info


def _avg_volume(daily: pd.DataFrame) -> float:
    if "Volume" not in daily.columns or len(daily) < 5:
        return 0.0
    v = _series_col(daily, "Volume").to_numpy()
    return float(np.mean(v[-20:])) if len(v) >= 20 else float(np.mean(v))


def _market_cap(symbol: str) -> float | None:
    try:
        t = yf.Ticker(symbol)
        fast = getattr(t, "fast_info", None)
        if fast is not None:
            cap = getattr(fast, "market_cap", None) or (fast.get("market_cap") if hasattr(fast, "get") else None)
            if cap:
                return float(cap)
        info = t.info or {}
        cap = info.get("marketCap")
        if cap:
            return float(cap)
    except Exception as ex:
        logging.debug("Method2 market cap skip %s: %s", symbol, ex)
    return None


def size_method2_capital(
    *,
    equity: float,
    entry_ref: float,
    stop_ref: float,
    risk_pct: float = 0.02,
    max_position_pct: float = 0.15,
) -> float:
    """Notional from 1–2% equity risk and stop distance, capped by max position %."""
    stop_dist = abs(float(entry_ref) - float(stop_ref))
    if stop_dist < 0.01 or entry_ref <= 0 or equity <= 0:
        return 0.0
    risk_usd = float(equity) * float(risk_pct)
    shares = risk_usd / stop_dist
    notional = shares * float(entry_ref)
    cap = float(equity) * float(max_position_pct)
    return round(min(notional, cap), 2)


def analyze_method2_daily(
    daily: pd.DataFrame,
    *,
    min_avg_volume: float = 1_000_000,
    min_atr_pct: float = 0.7,
) -> dict[str, Any] | None:
    """Analyze one symbol's daily OHLC for a pending method-2 setup."""
    if daily is None or len(daily) < 30:
        return None

    o = _series_col(daily, "Open").to_numpy()
    h = _series_col(daily, "High").to_numpy()
    l = _series_col(daily, "Low").to_numpy()
    c = _series_col(daily, "Close").to_numpy()

    avg_vol = _avg_volume(daily)
    if avg_vol < min_avg_volume:
        return None
    atr_pct = _atr_pct(h, l, c)
    if atr_pct < min_atr_pct:
        return None

    ok_htf, htf_info = htf_allows_trade(daily)
    if not ok_htf:
        return None

    types = classify_series(h, l)
    pending = detect_pending_trigger(types, o, h, l, c)
    if not pending:
        return None

    score = 5.0
    score += min(atr_pct, 5.0) * 0.3
    if htf_info.get("W") in (2, 3):
        score += 1.0
    if htf_info.get("M") in (2, 3):
        score += 1.0
    if htf_info.get("Q") in (2, 3):
        score += 0.5
    if htf_info.get("Y") in (2, 3):
        score += 0.5

    return {
        **pending,
        "pattern_score": round(score, 2),
        "atr_pct": round(atr_pct, 2),
        "avg_volume": round(avg_vol, 0),
        "htf": htf_info,
        "types_tail": types[-5:],
    }


def scan_method2(
    symbols: list[str],
    *,
    exclude: set[str] | None = None,
    equity: float = 1000.0,
    risk_pct: float = 0.02,
    max_position_pct: float = 0.15,
    min_market_cap: float = 300_000_000,
    min_avg_volume: float = 1_000_000,
    min_atr_pct: float = 0.7,
) -> Method2Hit | None:
    """Best שיטה 2 pending setup across symbols."""
    exclude = {s.upper() for s in (exclude or set())}
    best: Method2Hit | None = None

    for raw in symbols:
        symbol = str(raw).upper().strip()
        if not symbol or symbol in exclude:
            continue
        daily = fetch_daily_ohlc(symbol)
        if daily is None:
            continue
        analysis = analyze_method2_daily(
            daily,
            min_avg_volume=min_avg_volume,
            min_atr_pct=min_atr_pct,
        )
        if analysis is None:
            continue

        cap = _market_cap(symbol)
        if cap is not None and cap < min_market_cap:
            continue
        # Unknown market cap: still allow (best-effort)

        capital = size_method2_capital(
            equity=equity,
            entry_ref=float(analysis["entry_ref"]),
            stop_ref=float(analysis["stop_ref"]),
            risk_pct=risk_pct,
            max_position_pct=max_position_pct,
        )
        if capital < 10:
            continue

        reason = (
            f"{STRATEGY_LABEL_HE} · טריגר {analysis['trigger']} "
            f"(ממתין להשלמה מחר) · כניסה ~${analysis['entry_ref']:.2f} "
            f"סטופ ~${analysis['stop_ref']:.2f}"
        )
        hit = Method2Hit(
            symbol=symbol,
            trigger=str(analysis["trigger"]),
            pattern_score=float(analysis["pattern_score"]),
            close=float(analysis["close"]),
            entry_ref=float(analysis["entry_ref"]),
            stop_ref=float(analysis["stop_ref"]),
            reason_he=reason,
            capital_usd=capital,
            details={**analysis, "market_cap": cap},
        )
        if best is None or hit.pattern_score > best.pattern_score:
            best = hit
    return best
