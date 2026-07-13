"""Method 2 (שיטה 2): candle types 1/2/3 + multi-TF alignment + pending triggers.

Entry is a *pending* breakout (cent above/below the level) — never buy the open
just because a setup printed. Higher timeframes must agree on direction; weak
HTF closes (e.g. weekly near the low) are treated as conflicts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd
import yfinance as yf

STRATEGY_ID = "method2"
STRATEGY_LABEL_HE = "שיטה 2"

Side = Literal["LONG", "SHORT"]

# Pending daily sequences → expected trigger name for tomorrow
PENDING_TO_TRIGGER: dict[tuple[int, ...], str] = {
    (2, 1): "2-1-2",
    (3, 1): "3-1-2",
    (3,): "3-2",
    (3, 2): "3-2-2",
    (2, 2): "2-2-2",
}

# Close in bottom/top of range → conflict with that side
_WEAK_CLOSE_PCT = 0.35


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
    side: Side = "LONG"
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


def _close_location(h: float, l: float, c: float) -> float:
    """0 = at low, 1 = at high."""
    span = h - l
    if span <= 1e-9:
        return 0.5
    return float(np.clip((c - l) / span, 0.0, 1.0))


def bar_bias(
    o: float,
    h: float,
    l: float,
    c: float,
    prev_h: float,
    prev_l: float,
    kind: int,
) -> Literal["up", "down", "neutral"]:
    """Directional read of a 1/2/3 bar for HTF continuity."""
    loc = _close_location(h, l, c)
    if kind == 1:
        if loc >= 0.6:
            return "up"
        if loc <= 0.4:
            return "down"
        return "neutral"
    if kind == 2:
        took_high = h > prev_h
        took_low = l < prev_l
        if took_high and not took_low:
            return "up"
        if took_low and not took_high:
            return "down"
        return "up" if c >= o else "down"
    # type 3 outside — close location dominates
    if loc >= 0.55:
        return "up"
    if loc <= 0.45:
        return "down"
    return "up" if c >= o else "down"


def _bullish_bias_for_bar(
    o: float,
    h: float,
    l: float,
    c: float,
    prev_h: float,
    prev_l: float,
    kind: int,
) -> bool:
    return bar_bias(o, h, l, c, prev_h, prev_l, kind) == "up"


def _bearish_bias_for_bar(
    o: float,
    h: float,
    l: float,
    c: float,
    prev_h: float,
    prev_l: float,
    kind: int,
) -> bool:
    return bar_bias(o, h, l, c, prev_h, prev_l, kind) == "down"


def detect_pending_trigger(
    types: list[int],
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    *,
    side: Side = "LONG",
) -> dict[str, Any] | None:
    """After today's close, find a pending setup for tomorrow (not completed after the fact)."""
    if len(types) < 3:
        return None

    bias_fn = _bullish_bias_for_bar if side == "LONG" else _bearish_bias_for_bar

    for length in (2, 1):
        seq = tuple(types[-length:])
        trigger = PENDING_TO_TRIGGER.get(seq)
        if not trigger:
            continue

        if length == 2:
            i_break = -2
        else:
            i_break = -1

        prev_i = i_break - 1
        if abs(prev_i) > len(types):
            continue
        kind_break = types[i_break]
        if not bias_fn(
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
            trigger, seq, opens, highs, lows, closes, side=side
        )
        if entry_ref is None or stop_ref is None:
            continue
        if side == "LONG" and entry_ref <= stop_ref:
            continue
        if side == "SHORT" and entry_ref >= stop_ref:
            continue

        return {
            "trigger": trigger,
            "pending_seq": list(seq),
            "entry_ref": round(float(entry_ref), 4),
            "stop_ref": round(float(stop_ref), 4),
            "close": round(float(closes[-1]), 4),
            "side": side,
        }
    return None


def _levels_for_pending(
    trigger: str,
    seq: tuple[int, ...],
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    *,
    side: Side = "LONG",
) -> tuple[float | None, float | None]:
    """Reference entry/stop from completed bars (cent buffers). Long = break high; short = break low."""
    cent = 0.01
    if side == "LONG":
        if trigger in {"2-1-2", "3-1-2"} and seq[-1] == 1:
            return float(highs[-1]) + cent, float(lows[-1]) - cent
        if trigger == "3-2" and seq == (3,):
            return float(highs[-1]) + cent, float(opens[-1])
        if trigger == "3-2-2" and seq == (3, 2):
            return float(highs[-1]) + cent, float(opens[-1]) - cent
        if trigger == "2-2-2" and seq == (2, 2):
            return float(highs[-2]) + cent, float(opens[-2]) - cent
        return None, None

    # SHORT — mirror: entry cent below the level, stop above
    if trigger in {"2-1-2", "3-1-2"} and seq[-1] == 1:
        return float(lows[-1]) - cent, float(highs[-1]) + cent
    if trigger == "3-2" and seq == (3,):
        return float(lows[-1]) - cent, float(opens[-1])
    if trigger == "3-2-2" and seq == (3, 2):
        return float(lows[-1]) - cent, float(opens[-1]) + cent
    if trigger == "2-2-2" and seq == (2, 2):
        return float(lows[-2]) - cent, float(opens[-2]) + cent
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


def _frame_htf_read(frame: pd.DataFrame) -> dict[str, Any] | None:
    if frame is None or len(frame) < 2:
        return None
    o = _series_col(frame, "Open").to_numpy()
    h = _series_col(frame, "High").to_numpy()
    l = _series_col(frame, "Low").to_numpy()
    c = _series_col(frame, "Close").to_numpy()
    kind = classify_bar(float(h[-2]), float(l[-2]), float(h[-1]), float(l[-1]))
    bias = bar_bias(
        float(o[-1]),
        float(h[-1]),
        float(l[-1]),
        float(c[-1]),
        float(h[-2]),
        float(l[-2]),
        kind,
    )
    loc = _close_location(float(h[-1]), float(l[-1]), float(c[-1]))
    return {
        "kind": kind,
        "bias": bias,
        "close_loc": round(loc, 3),
        "weak_long": loc <= _WEAK_CLOSE_PCT,
        "weak_short": loc >= (1.0 - _WEAK_CLOSE_PCT),
    }


def htf_allows_trade(
    daily: pd.DataFrame,
    *,
    side: Side = "LONG",
) -> tuple[bool, dict[str, Any]]:
    """Require HTF continuity in `side`; reject inside W/M and weak opposing closes."""
    info: dict[str, Any] = {"side": side}
    if not isinstance(daily.index, pd.DatetimeIndex):
        daily = daily.copy()
        daily.index = pd.to_datetime(daily.index)

    frames = {
        "W": _resample_ohlc(daily, "W-FRI"),
        "M": _resample_ohlc(daily, "ME"),
    }
    monthly = frames["M"]
    if len(monthly) >= 4:
        frames["Q"] = _resample_ohlc(monthly, "QE")
    if len(monthly) >= 12:
        frames["Y"] = _resample_ohlc(monthly, "YE")

    reads: dict[str, Any] = {}
    for name, frame in frames.items():
        reads[name] = _frame_htf_read(frame)
        info[name] = None if reads[name] is None else reads[name]["kind"]
        if reads[name] is not None:
            info[f"{name}_bias"] = reads[name]["bias"]
            info[f"{name}_close_loc"] = reads[name]["close_loc"]

    w = reads.get("W")
    m = reads.get("M")
    if w is None or m is None:
        return False, info

    # Inside / discovery on W or M — wait
    if w["kind"] == 1 or m["kind"] == 1:
        info["reject"] = "htf_inside"
        return False, info

    want = "up" if side == "LONG" else "down"
    oppose = "down" if side == "LONG" else "up"

    # Core continuity: weekly must not oppose the trade
    if w["bias"] == oppose:
        info["reject"] = "weekly_opposes"
        return False, info
    if m["bias"] == oppose:
        info["reject"] = "monthly_opposes"
        return False, info

    # Weak close near the wrong extreme (LABU-style: "green" structure, close near low)
    if side == "LONG" and w["weak_long"]:
        info["reject"] = "weekly_weak_close"
        return False, info
    if side == "SHORT" and w["weak_short"]:
        info["reject"] = "weekly_weak_close"
        return False, info

    # Prefer at least one of W/M actively with us
    if w["bias"] != want and m["bias"] != want:
        info["reject"] = "no_htf_continuation"
        return False, info

    info["aligned"] = True
    return True, info


def resolve_method2_fill(
    rec: dict[str, Any],
    bar: dict[str, float],
) -> float | None:
    """Return fill price if the pending breakout triggered today; else None (skip).

    Long: need high >= entry_ref; skip if open already below stop.
    Short: need low <= entry_ref; skip if open already above stop.
    """
    side = str(rec.get("side") or "LONG").upper()
    entry_ref = float(rec.get("method2_entry_ref") or rec.get("entry_ref_price") or 0)
    stop_ref = float(rec.get("method2_stop_ref") or rec.get("stop_loss_price") or rec.get("floor_price") or 0)
    if entry_ref <= 0 or stop_ref <= 0:
        return None

    o = float(bar["open"])
    h = float(bar["high"])
    l = float(bar["low"])

    if side == "SHORT":
        if o > stop_ref:
            return None  # gapped through stop — invalid
        if l > entry_ref:
            return None  # no downside breakout
        # Fill at entry_ref unless open already through it
        return round(min(o, entry_ref), 4)

    # LONG
    if o < stop_ref:
        return None  # gapped below stop — do not chase
    if h < entry_ref:
        return None  # breakout never printed
    return round(max(o, entry_ref), 4)


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
    allow_short: bool = True,
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

    types = classify_series(h, l)
    best: dict[str, Any] | None = None

    for side in (("LONG", "SHORT") if allow_short else ("LONG",)):
        ok_htf, htf_info = htf_allows_trade(daily, side=side)  # type: ignore[arg-type]
        if not ok_htf:
            continue
        pending = detect_pending_trigger(types, o, h, l, c, side=side)  # type: ignore[arg-type]
        if not pending:
            continue

        score = 5.0
        score += min(atr_pct, 5.0) * 0.3
        if htf_info.get("W_bias") == ("up" if side == "LONG" else "down"):
            score += 1.5
        if htf_info.get("M_bias") == ("up" if side == "LONG" else "down"):
            score += 1.0
        if htf_info.get("Q") in (2, 3):
            score += 0.5
        if htf_info.get("Y") in (2, 3):
            score += 0.5
        # Prefer continuity over reversal-looking 2-2-2 when HTF is only weakly aligned
        if pending["trigger"] == "2-2-2" and htf_info.get("W_bias") != (
            "up" if side == "LONG" else "down"
        ):
            score -= 1.0

        candidate = {
            **pending,
            "pattern_score": round(score, 2),
            "atr_pct": round(atr_pct, 2),
            "avg_volume": round(avg_vol, 0),
            "htf": htf_info,
            "types_tail": types[-5:],
        }
        if best is None or candidate["pattern_score"] > best["pattern_score"]:
            best = candidate

    return best


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
    allow_short: bool = True,
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
            allow_short=allow_short,
        )
        if analysis is None:
            continue

        cap = _market_cap(symbol)
        if cap is not None and cap < min_market_cap:
            continue

        capital = size_method2_capital(
            equity=equity,
            entry_ref=float(analysis["entry_ref"]),
            stop_ref=float(analysis["stop_ref"]),
            risk_pct=risk_pct,
            max_position_pct=max_position_pct,
        )
        if capital < 10:
            continue

        side = str(analysis.get("side") or "LONG")
        side_he = "לונג" if side == "LONG" else "שורט"
        reason = (
            f"{STRATEGY_LABEL_HE} · {side_he} · טריגר {analysis['trigger']} "
            f"(ממתין לפריצה) · כניסה ~${analysis['entry_ref']:.2f} "
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
            side=side if side in ("LONG", "SHORT") else "LONG",  # type: ignore[arg-type]
            details={**analysis, "market_cap": cap},
        )
        if best is None or hit.pattern_score > best.pattern_score:
            best = hit
    return best


def fetch_intraday_ohlc(
    symbol: str,
    *,
    interval: str = "5m",
    period: str = "5d",
) -> pd.DataFrame | None:
    """Intraday OHLC for micro triggers (5m / 1m)."""
    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as ex:
        logging.debug("Method2 intraday OHLC failed %s %s: %s", symbol, interval, ex)
        return None
    df = _flatten_ohlc(df)
    if df is None or df.empty or len(df) < 8:
        return None
    need = {"Open", "High", "Low", "Close"}
    if not need.issubset(df.columns):
        return None
    out = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index)
    return out


def session_bar_from_intraday(df: pd.DataFrame) -> dict[str, float] | None:
    """Aggregate today's (or last session) intraday bars into one OHLC bar."""
    if df is None or df.empty:
        return None
    if not isinstance(df.index, pd.DatetimeIndex):
        df = df.copy()
        df.index = pd.to_datetime(df.index)
    # Prefer bars from the latest calendar day in the frame
    last_day = df.index[-1].date()
    day = df[df.index.date == last_day]
    if day.empty:
        day = df
    o = float(_series_col(day, "Open").iloc[0])
    h = float(_series_col(day, "High").max())
    l = float(_series_col(day, "Low").min())
    c = float(_series_col(day, "Close").iloc[-1])
    return {"open": o, "high": h, "low": l, "close": c}


def _micro_breakout_fill(
    df: pd.DataFrame,
    *,
    side: Side,
    daily_entry: float,
    daily_stop: float,
) -> dict[str, Any] | None:
    """If a 5m/1m pending setup just broke in the daily direction, return a fill.

    The micro entry must reach the daily breakout level (or price already did) —
    this is the 'intraday trigger that leads into the daily break' case.
    """
    if df is None or len(df) < 10:
        return None
    # Use closed bars for the pending setup; last bar is the live/breakout bar
    closed = df.iloc[:-1]
    live = df.iloc[-1]
    o = _series_col(closed, "Open").to_numpy()
    h = _series_col(closed, "High").to_numpy()
    l = _series_col(closed, "Low").to_numpy()
    c = _series_col(closed, "Close").to_numpy()
    types = classify_series(h, l)
    pending = detect_pending_trigger(types, o, h, l, c, side=side)
    if not pending:
        return None

    micro_entry = float(pending["entry_ref"])
    micro_stop = float(pending["stop_ref"])
    live_o = float(live["Open"])
    live_h = float(live["High"])
    live_l = float(live["Low"])

    if side == "LONG":
        if live_o < daily_stop or live_o < micro_stop:
            return None
        if live_h < micro_entry:
            return None
        # Micro breakout must be at/through the daily level (or daily already tagged)
        if micro_entry < daily_entry - 0.02 and live_h < daily_entry:
            return None
        fill = max(live_o, micro_entry, daily_entry) if live_h >= daily_entry else max(live_o, micro_entry)
        return {
            "fill_price": round(float(fill), 4),
            "reason": "micro_trigger",
            "micro_trigger": pending["trigger"],
            "micro_entry": micro_entry,
        }

    # SHORT
    if live_o > daily_stop or live_o > micro_stop:
        return None
    if live_l > micro_entry:
        return None
    if micro_entry > daily_entry + 0.02 and live_l > daily_entry:
        return None
    fill = min(live_o, micro_entry, daily_entry) if live_l <= daily_entry else min(live_o, micro_entry)
    return {
        "fill_price": round(float(fill), 4),
        "reason": "micro_trigger",
        "micro_trigger": pending["trigger"],
        "micro_entry": micro_entry,
    }


def evaluate_method2_intraday_entry(
    rec: dict[str, Any],
    *,
    intervals: tuple[str, ...] = ("5m", "1m"),
) -> dict[str, Any] | None:
    """Check whether a pending שיטה 2 breakout can fill now (daily level or micro TF)."""
    symbol = str(rec.get("symbol") or "").upper()
    if not symbol:
        return None
    side = str(rec.get("side") or "LONG").upper()
    if side not in ("LONG", "SHORT"):
        side = "LONG"
    daily_entry = float(rec.get("method2_entry_ref") or rec.get("entry_ref_price") or 0)
    daily_stop = float(
        rec.get("method2_stop_ref") or rec.get("stop_loss_price") or rec.get("floor_price") or 0
    )
    if daily_entry <= 0 or daily_stop <= 0:
        return None

    df5 = fetch_intraday_ohlc(symbol, interval="5m", period="5d")
    if df5 is None:
        return None
    session = session_bar_from_intraday(df5)
    if session is None:
        return None

    # Gap through stop → setup dead for the day
    if side == "LONG" and session["open"] < daily_stop:
        return {"fill_price": None, "reason": "invalidated", "interval": "5m"}
    if side == "SHORT" and session["open"] > daily_stop:
        return {"fill_price": None, "reason": "invalidated", "interval": "5m"}

    # Primary: daily level break using session aggregate from 5m
    level_fill = resolve_method2_fill(rec, session)
    if level_fill is not None:
        return {
            "fill_price": level_fill,
            "reason": "daily_level_break",
            "interval": "5m",
            "session": session,
        }

    for interval in intervals:
        df = df5 if interval == "5m" else fetch_intraday_ohlc(symbol, interval=interval, period="1d")
        if df is None:
            continue
        # Focus on today's bars when possible
        if isinstance(df.index, pd.DatetimeIndex):
            last_day = df.index[-1].date()
            day_df = df[df.index.date == last_day]
            if len(day_df) >= 10:
                df = day_df
        micro = _micro_breakout_fill(
            df,
            side=side,  # type: ignore[arg-type]
            daily_entry=daily_entry,
            daily_stop=daily_stop,
        )
        if micro and micro.get("fill_price"):
            micro["interval"] = interval
            micro["session"] = session
            return micro
    return None


def is_method2_rec(rec: dict[str, Any]) -> bool:
    return str(rec.get("strategy") or "") == "method2" or bool(rec.get("sleeve"))


def pending_method2_recs(plan: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    """Approved שיטה 2 picks still waiting for breakout fill."""
    from trading_pulse.agent.positions import held_symbols

    held = held_symbols(state)
    out: list[dict[str, Any]] = []
    for rec in plan.get("recommendations") or []:
        if not rec.get("approved"):
            continue
        if not is_method2_rec(rec):
            continue
        status = str(rec.get("method2_status") or "")
        if status in {"filled", "invalidated", "expired"}:
            continue
        sym = str(rec.get("symbol") or "").upper()
        if not sym or sym in held:
            continue
        out.append(rec)
    return out
