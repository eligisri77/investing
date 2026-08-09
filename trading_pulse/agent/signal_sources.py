"""Aggregate trading signals from multiple public market-data sources."""

from __future__ import annotations

import logging
import os
import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import pandas as pd
import requests
import yfinance as yf

from trading_pulse.agent.theme_boost import theme_score_bonus, theme_tags

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
}

SOURCE_LABELS: dict[str, str] = {
    "yahoo": "Yahoo Finance",
    "finviz": "Finviz",
    "nasdaq": "Nasdaq",
    "alphavantage": "Alpha Vantage",
    "finnhub": "Finnhub",
    "alpaca": "Alpaca",
    "cnbc": "CNBC",
    "barchart": "Barchart",
}

DEFAULT_SIGNAL_SOURCES = [
    "yahoo",
    "finviz",
    "nasdaq",
    "alphavantage",
    "finnhub",
    "alpaca",
]

DEFAULT_SOURCE_WEIGHTS: dict[str, float] = {
    "yahoo": 1.0,
    "nasdaq": 1.0,
    "finviz": 0.75,
    "alphavantage": 1.0,
    "finnhub": 1.0,
    "alpaca": 1.0,
    "cnbc": 0.25,
    "barchart": 0.25,
}

DEFAULT_MAX_SOURCE_SCORE_STD = 4.5
DEFAULT_MAX_SOURCE_SCORE_SPREAD = 9.0
DEFAULT_DISAGREEMENT_SCORE_PENALTY = 0.75

ETF_SYMBOLS = {
    "TQQQ",
    "SOXL",
    "LABU",
    "SPY",
    "QQQ",
    "IWM",
    "XLF",
    "XLE",
    "XLK",
}


@dataclass
class SourceSignal:
    source: str
    score: float
    close: float | None = None
    ret_5d: float | None = None
    ret_5d_pct: float | None = None
    ret_1d: float | None = None
    ret_1d_pct: float | None = None
    ret_2d: float | None = None
    vol_ratio: float | None = None
    atr_pct: float | None = None
    near_high_pct: float | None = None
    breakout_ok: bool = False
    volume_ok: bool = False
    above_ma20_pct: float | None = None
    momentum_ok: bool = False
    down_days_last_3: int = 0
    up_days_last_5: int = 0
    down_days_last_5: int = 0
    range_5d_pct: float | None = None
    zigzag_in_range: bool = False
    pullback_ok: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


# Trend + pullback scoring bands (percent / fractions as noted).
_PULLBACK_NEAR_HIGH_MIN = -8.0  # % below 20d high — deepest sweet-spot edge
_PULLBACK_NEAR_HIGH_MAX = -2.0  # % below 20d high — shallowest sweet-spot edge
_CHASE_NEAR_HIGH = -1.0  # above this (closer to high) → chase penalty
_RET_5D_CHASE = 0.15  # +15% in 5d → already ran hard
_RANGE_5D_MAX_PCT = 8.0  # consolidation band for zigzag bonus


def _extract_series(df: pd.DataFrame, col: str) -> pd.Series:
    series = df[col]
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    return series


def _parse_number(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = re.sub(r"[^\d.+-]", "", str(text).replace(",", ""))
    if not cleaned or cleaned in {".", "+", "-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_pct(text: str | None) -> float | None:
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    token = raw.split()[0]
    value = _parse_number(token)
    if value is None:
        return None
    if "%" in raw or abs(value) > 3:
        return value
    return value * 100


def _ohlcv_metrics(df: pd.DataFrame) -> dict[str, Any] | None:
    if df.empty or len(df) < 25:
        return None
    df = df.dropna()
    if len(df) < 25:
        return None
    close = _extract_series(df, "Close")
    high = _extract_series(df, "High")
    low = _extract_series(df, "Low")
    volume = _extract_series(df, "Volume")
    last_close = float(close.iloc[-1])
    last_vol = float(volume.iloc[-1])
    avg_vol20 = float(volume.rolling(20).mean().iloc[-1])
    ma20 = float(close.rolling(20).mean().iloc[-1])
    high_20 = float(close.rolling(20).max().iloc[-1])
    ret_5d = (last_close / float(close.iloc[-6])) - 1 if len(close) >= 6 else 0.0
    ret_1d = (last_close / float(close.iloc[-2])) - 1 if len(close) >= 2 else 0.0
    ret_2d = (last_close / float(close.iloc[-3])) - 1 if len(close) >= 3 else 0.0
    # Daily direction from close-to-close (last 5 completed moves ending at today).
    day_rets = close.pct_change().iloc[-5:]
    down_flags = [bool(float(r) < 0) for r in day_rets.dropna().tolist()]
    while len(down_flags) < 5:
        down_flags.insert(0, False)
    down_days_last_3 = sum(1 for d in down_flags[-3:] if d)
    down_days_last_5 = sum(1 for d in down_flags if d)
    up_days_last_5 = sum(1 for d in down_flags if not d)
    hi_5 = float(high.iloc[-5:].max()) if len(high) >= 5 else float(high.max())
    lo_5 = float(low.iloc[-5:].min()) if len(low) >= 5 else float(low.min())
    range_5d_pct = ((hi_5 - lo_5) / last_close * 100) if last_close > 0 else 0.0
    zigzag_in_range = bool(
        up_days_last_5 >= 2
        and down_days_last_5 >= 2
        and range_5d_pct <= _RANGE_5D_MAX_PCT
    )
    vol_ratio = float(last_vol / avg_vol20) if avg_vol20 > 0 else 0.0
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])
    atr_pct = (atr / last_close * 100) if last_close > 0 else 0.0
    near_high_pct = ((last_close / high_20) - 1) * 100 if high_20 > 0 else 0.0
    above_ma20_pct = ((last_close / ma20) - 1) * 100 if ma20 > 0 else 0.0
    momentum_ok = bool(last_close > ma20)
    pullback_day = bool(ret_1d < 0 or down_days_last_3 >= 2)
    in_pullback_band = bool(
        _PULLBACK_NEAR_HIGH_MIN <= near_high_pct <= _PULLBACK_NEAR_HIGH_MAX
    )
    pullback_ok = bool(
        momentum_ok
        and ((pullback_day and in_pullback_band) or zigzag_in_range)
    )
    return {
        "close": last_close,
        "ret_5d": float(ret_5d),
        "ret_5d_pct": float(ret_5d * 100),
        "ret_1d": float(ret_1d),
        "ret_1d_pct": float(ret_1d * 100),
        "ret_2d": float(ret_2d),
        "vol_ratio": vol_ratio,
        "atr_pct": float(atr_pct),
        "near_high_pct": float(near_high_pct),
        "breakout_ok": bool(last_close >= high_20 * 0.98),
        "volume_ok": bool(vol_ratio >= 1.0),
        "above_ma20_pct": float(above_ma20_pct),
        "momentum_ok": momentum_ok,
        "down_days_last_3": int(down_days_last_3),
        "up_days_last_5": int(up_days_last_5),
        "down_days_last_5": int(down_days_last_5),
        "range_5d_pct": float(range_5d_pct),
        "zigzag_in_range": zigzag_in_range,
        "pullback_ok": pullback_ok,
        "avg_vol20": float(avg_vol20),
    }


def _ensure_market_env() -> None:
    from trading_pulse.core.env_config import _load_dotenv

    _load_dotenv(override=True)


def _env_key(name: str) -> str:
    _ensure_market_env()
    return os.environ.get(name, "").strip()


def _ohlcv_df_from_series(
    *,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
) -> pd.DataFrame:
    if not closes or len(closes) != len(highs) or len(closes) != len(lows) or len(closes) != len(volumes):
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "Close": closes,
            "High": highs,
            "Low": lows,
            "Volume": volumes,
        }
    )


def _signal_from_ohlcv_df(source: str, df: pd.DataFrame, speculative: bool) -> SourceSignal | None:
    metrics = _ohlcv_metrics(df)
    if metrics is None:
        return None
    return _metrics_to_signal(source, metrics, speculative)


def _pullback_components(metrics: dict[str, Any]) -> dict[str, float]:
    """Shared trend + pullback terms used by both score profiles."""
    momentum_ok = bool(metrics.get("momentum_ok", False))
    near_high = float(metrics.get("near_high_pct") or 0.0)
    ret_1d = float(metrics.get("ret_1d") or 0.0)
    ret_5d = float(metrics.get("ret_5d") or 0.0)
    down_3 = int(metrics.get("down_days_last_3") or 0)
    zigzag = bool(metrics.get("zigzag_in_range", False))
    vol_ratio = float(metrics.get("vol_ratio") or 0.0)

    trend = 4.0 if momentum_ok else -5.0

    pullback = 0.0
    if ret_1d < 0:
        pullback += 2.0
    if down_3 >= 2:
        pullback += 1.5
    if zigzag:
        pullback += 1.0
    if _PULLBACK_NEAR_HIGH_MIN <= near_high <= _PULLBACK_NEAR_HIGH_MAX:
        pullback += 2.0

    chase = 0.0
    if near_high > _CHASE_NEAR_HIGH:
        chase -= 3.0
    if ret_5d > _RET_5D_CHASE:
        chase -= 2.5

    # Mild medium-term drift: prefer slight positive 5d, not a blow-off.
    medium = max(min(ret_5d, 0.12), -0.08) * 8.0
    vol = max(min((vol_ratio - 1.0) * 1.5, 1.5), -1.0)

    return {
        "trend": trend,
        "pullback": pullback,
        "chase": chase,
        "medium": medium,
        "vol": vol,
    }


def score_momentum(metrics: dict[str, Any]) -> float:
    """Uptrend + short pullback — not chasing fresh highs after a rally."""
    c = _pullback_components(metrics)
    return float(c["trend"] + c["pullback"] + c["chase"] + c["medium"] + c["vol"])


def score_speculative(metrics: dict[str, Any]) -> float:
    """Same pullback core; light ATR spice without rewarding being at the high."""
    c = _pullback_components(metrics)
    atr_pct = float(metrics.get("atr_pct") or 0.0)
    # Prefer moderate volatility near a pullback, not max ATR at highs.
    atr_term = min(max(atr_pct, 0.0), 8.0) * 0.25
    return float(
        c["trend"] + c["pullback"] + c["chase"] + c["medium"] + c["vol"] + atr_term
    )


def _metrics_to_signal(source: str, metrics: dict[str, Any], speculative: bool) -> SourceSignal:
    score = score_speculative(metrics) if speculative else score_momentum(metrics)
    return SourceSignal(
        source=source,
        score=score,
        close=metrics.get("close"),
        ret_5d=metrics.get("ret_5d"),
        ret_5d_pct=metrics.get("ret_5d_pct"),
        ret_1d=metrics.get("ret_1d"),
        ret_1d_pct=metrics.get("ret_1d_pct"),
        ret_2d=metrics.get("ret_2d"),
        vol_ratio=metrics.get("vol_ratio"),
        atr_pct=metrics.get("atr_pct"),
        near_high_pct=metrics.get("near_high_pct"),
        breakout_ok=bool(metrics.get("breakout_ok", False)),
        volume_ok=bool(metrics.get("volume_ok", False)),
        above_ma20_pct=metrics.get("above_ma20_pct"),
        momentum_ok=bool(metrics.get("momentum_ok", False)),
        down_days_last_3=int(metrics.get("down_days_last_3") or 0),
        up_days_last_5=int(metrics.get("up_days_last_5") or 0),
        down_days_last_5=int(metrics.get("down_days_last_5") or 0),
        range_5d_pct=metrics.get("range_5d_pct"),
        zigzag_in_range=bool(metrics.get("zigzag_in_range", False)),
        pullback_ok=bool(metrics.get("pullback_ok", False)),
        extra={"avg_vol20": metrics.get("avg_vol20")},
    )


def _partial_metrics_to_signal(
    source: str,
    *,
    close: float | None,
    change_pct: float | None = None,
    perf_week_pct: float | None = None,
    vol_ratio: float | None = None,
    atr_pct: float | None = None,
    near_high_pct: float | None = None,
    speculative: bool,
) -> SourceSignal | None:
    ret_5d = None
    if perf_week_pct is not None:
        ret_5d = perf_week_pct / 100.0
    elif change_pct is not None:
        ret_5d = change_pct / 100.0
    if close is None and ret_5d is None and vol_ratio is None and atr_pct is None:
        return None

    # Non-OHLCV sources lack daily bars — approximate pullback from daily change.
    ret_1d = (change_pct / 100.0) if change_pct is not None else 0.0
    nh = near_high_pct if near_high_pct is not None else 0.0
    momentum_ok = bool(change_pct is not None and change_pct > 0) or bool(
        (perf_week_pct or 0) > 0 and ret_1d < 0
    )
    down_3 = 1 if ret_1d < 0 else 0
    in_band = _PULLBACK_NEAR_HIGH_MIN <= nh <= _PULLBACK_NEAR_HIGH_MAX
    metrics = {
        "close": close or 0.0,
        "ret_5d": ret_5d or 0.0,
        "ret_5d_pct": (ret_5d or 0.0) * 100,
        "ret_1d": ret_1d,
        "ret_1d_pct": ret_1d * 100,
        "ret_2d": ret_1d,
        "vol_ratio": vol_ratio or 1.0,
        "atr_pct": atr_pct or 0.0,
        "near_high_pct": nh,
        "breakout_ok": bool(near_high_pct is not None and near_high_pct >= -2.0),
        "volume_ok": bool(vol_ratio is not None and vol_ratio >= 1.0),
        "above_ma20_pct": change_pct or 0.0,
        "momentum_ok": momentum_ok,
        "down_days_last_3": down_3,
        "up_days_last_5": 0,
        "down_days_last_5": down_3,
        "range_5d_pct": 0.0,
        "zigzag_in_range": False,
        "pullback_ok": bool(momentum_ok and ret_1d < 0 and in_band),
    }
    return _metrics_to_signal(source, metrics, speculative)


def fetch_finviz_snapshot(ticker: str) -> dict[str, str]:
    response = requests.get(
        f"https://finviz.com/quote.ashx?t={ticker}",
        headers={**HTTP_HEADERS, "Referer": "https://finviz.com/"},
        timeout=20,
    )
    response.raise_for_status()
    rows = re.findall(
        r'snapshot-td-label">([^<]+)</div></td><td[^>]*>.*?snapshot-td-content">(.*?)</div></td>',
        response.text,
        re.S,
    )
    out: dict[str, str] = {}
    for key, value in rows:
        out[key.strip()] = re.sub(r"<[^>]+>", "", value).strip()
    return out


def fetch_yahoo_signal(ticker: str, speculative: bool) -> SourceSignal | None:
    df = yf.download(
        ticker,
        period="3mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if df.empty:
        return None
    metrics = _ohlcv_metrics(df)
    if metrics is None:
        return None
    return _metrics_to_signal("yahoo", metrics, speculative)


def fetch_finviz_signal(ticker: str, speculative: bool) -> SourceSignal | None:
    snap = fetch_finviz_snapshot(ticker)
    close = _parse_number(snap.get("Price"))
    change_pct = _parse_pct(snap.get("Change"))
    perf_week_pct = _parse_pct(snap.get("Perf Week"))
    rel_volume = _parse_number(snap.get("Rel Volume"))
    atr_val = _parse_number(snap.get("ATR (14)"))
    atr_pct = (atr_val / close * 100) if atr_val and close else None
    if atr_pct is None:
        volatility = snap.get("Volatility", "")
        if volatility:
            week_vol = _parse_pct(volatility.split()[0])
            atr_pct = week_vol

    near_high_pct = None
    high_52 = snap.get("52W High", "")
    if high_52 and close:
        pct_from_high = _parse_pct(high_52.split()[-1] if " " in high_52 else high_52)
        if pct_from_high is not None:
            near_high_pct = -abs(pct_from_high)

    return _partial_metrics_to_signal(
        "finviz",
        close=close,
        change_pct=change_pct,
        perf_week_pct=perf_week_pct,
        vol_ratio=rel_volume,
        atr_pct=atr_pct,
        near_high_pct=near_high_pct,
        speculative=speculative,
    )


def fetch_cnbc_signal(ticker: str, speculative: bool) -> SourceSignal | None:
    response = requests.get(
        "https://quote.cnbc.com/quote-html-webservice/quote.htm"
        f"?symbols={ticker}&requestMethod=quick&noform=1&partnerId=2&fund=1&exthrs=0&output=json",
        headers=HTTP_HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    quotes = response.json().get("QuickQuoteResult", {}).get("QuickQuote", [])
    if not quotes:
        return None
    quote = quotes[0]
    close = _parse_number(quote.get("last"))
    change_pct = _parse_number(quote.get("change_pct"))
    volume = _parse_number(str(quote.get("fullVolume") or quote.get("volume") or "").replace(",", ""))
    vol_ratio = None
    if volume and volume > 0:
        vol_ratio = max(volume / 50_000_000, 0.1)
    return _partial_metrics_to_signal(
        "cnbc",
        close=close,
        change_pct=change_pct,
        vol_ratio=vol_ratio,
        speculative=speculative,
    )


def fetch_barchart_signal(ticker: str, speculative: bool) -> SourceSignal | None:
    response = requests.get(
        f"https://www.barchart.com/stocks/quotes/{ticker}",
        headers=HTTP_HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    last_match = re.search(r'"lastPrice":"([0-9.]+)"', response.text)
    last = _parse_number(last_match.group(1)) if last_match else None
    pct_match = re.search(r'"percentChange":([0-9.-]+)', response.text)
    change_pct = float(pct_match.group(1)) * 100 if pct_match else None
    return _partial_metrics_to_signal(
        "barchart",
        close=last,
        change_pct=change_pct,
        speculative=speculative,
    )


def _nasdaq_asset_class(ticker: str) -> str:
    return "etf" if ticker.upper() in ETF_SYMBOLS else "stocks"


def _nasdaq_bars_to_df(bars: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for bar in bars:
        z = bar.get("z", {})
        close = _parse_number(z.get("close"))
        if close is None:
            continue
        rows.append(
            {
                "Close": close,
                "High": _parse_number(z.get("high")) or close,
                "Low": _parse_number(z.get("low")) or close,
                "Open": _parse_number(z.get("open")) or close,
                "Volume": _parse_number(str(z.get("volume", "")).replace(",", "")) or 0.0,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _fetch_nasdaq_chart(ticker: str, asset: str, start: date, end: date) -> tuple[dict[str, Any], pd.DataFrame]:
    response = requests.get(
        "https://api.nasdaq.com/api/quote/"
        f"{ticker}/chart?assetclass={asset}"
        f"&fromdate={start.isoformat()}&todate={end.isoformat()}",
        headers={
            **HTTP_HEADERS,
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/",
        },
        timeout=25,
    )
    response.raise_for_status()
    data = response.json().get("data") or {}
    bars = data.get("chart") or []
    return data, _nasdaq_bars_to_df(bars)


def fetch_nasdaq_signal(ticker: str, speculative: bool) -> SourceSignal | None:
    end = date.today()
    start = end - timedelta(days=100)
    asset = _nasdaq_asset_class(ticker)
    data, df = _fetch_nasdaq_chart(ticker, asset, start, end)
    metrics = _ohlcv_metrics(df)
    if metrics is None and asset == "stocks":
        data, df = _fetch_nasdaq_chart(ticker, "etf", start, end)
        metrics = _ohlcv_metrics(df)
    if metrics is not None:
        return _metrics_to_signal("nasdaq", metrics, speculative)

    change_pct = _parse_pct(data.get("percentageChange"))
    close = _parse_number(data.get("lastSalePrice"))
    return _partial_metrics_to_signal(
        "nasdaq",
        close=close,
        change_pct=change_pct,
        speculative=speculative,
    )


def fetch_alphavantage_signal(ticker: str, speculative: bool) -> SourceSignal | None:
    api_key = _env_key("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        return None
    response = requests.get(
        "https://www.alphavantage.co/query",
        params={
            "function": "TIME_SERIES_DAILY",
            "symbol": ticker,
            "outputsize": "compact",
            "apikey": api_key,
        },
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("Note") or payload.get("Information"):
        logging.warning("Alpha Vantage rate/info for %s: %s", ticker, payload.get("Note") or payload.get("Information"))
        return None
    series = payload.get("Time Series (Daily)") or {}
    if not series:
        return None
    rows: list[tuple[str, float, float, float, float]] = []
    for day_str, bar in series.items():
        close = _parse_number(bar.get("4. close"))
        high = _parse_number(bar.get("2. high"))
        low = _parse_number(bar.get("3. low"))
        volume = _parse_number(bar.get("5. volume"))
        if close is None or high is None or low is None or volume is None:
            continue
        rows.append((day_str, close, high, low, volume))
    if not rows:
        return None
    rows.sort(key=lambda item: item[0])
    df = _ohlcv_df_from_series(
        closes=[r[1] for r in rows],
        highs=[r[2] for r in rows],
        lows=[r[3] for r in rows],
        volumes=[r[4] for r in rows],
    )
    return _signal_from_ohlcv_df("alphavantage", df, speculative)


def fetch_finnhub_signal(ticker: str, speculative: bool) -> SourceSignal | None:
    api_key = _env_key("FINNHUB_API_KEY")
    if not api_key:
        return None
    end = int(datetime.now(timezone.utc).timestamp())
    start = end - 120 * 86400
    response = requests.get(
        "https://finnhub.io/api/v1/stock/candle",
        params={
            "symbol": ticker.upper(),
            "resolution": "D",
            "from": start,
            "to": end,
            "token": api_key,
        },
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("s") != "ok":
        return None
    df = _ohlcv_df_from_series(
        closes=[float(x) for x in payload.get("c", [])],
        highs=[float(x) for x in payload.get("h", [])],
        lows=[float(x) for x in payload.get("l", [])],
        volumes=[float(x) for x in payload.get("v", [])],
    )
    return _signal_from_ohlcv_df("finnhub", df, speculative)


def fetch_alpaca_signal(ticker: str, speculative: bool) -> SourceSignal | None:
    key_id = _env_key("ALPACA_API_KEY_ID")
    secret = _env_key("ALPACA_API_SECRET_KEY")
    if not key_id or not secret:
        return None
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=120)
    response = requests.get(
        f"https://data.alpaca.markets/v2/stocks/{ticker.upper()}/bars",
        params={
            "timeframe": "1Day",
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limit": 100,
            "adjustment": "split",
        },
        headers={
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret,
        },
        timeout=25,
    )
    response.raise_for_status()
    bars = response.json().get("bars") or []
    if not bars:
        return None
    df = _ohlcv_df_from_series(
        closes=[float(b["c"]) for b in bars],
        highs=[float(b["h"]) for b in bars],
        lows=[float(b["l"]) for b in bars],
        volumes=[float(b["v"]) for b in bars],
    )
    return _signal_from_ohlcv_df("alpaca", df, speculative)


SOURCE_FETCHERS: dict[str, Callable[[str, bool], SourceSignal | None]] = {
    "yahoo": fetch_yahoo_signal,
    "finviz": fetch_finviz_signal,
    "cnbc": fetch_cnbc_signal,
    "barchart": fetch_barchart_signal,
    "nasdaq": fetch_nasdaq_signal,
    "alphavantage": fetch_alphavantage_signal,
    "finnhub": fetch_finnhub_signal,
    "alpaca": fetch_alpaca_signal,
}


def fetch_all_source_signals(
    ticker: str,
    sources: list[str],
    speculative: bool,
) -> list[SourceSignal]:
    signals: list[SourceSignal] = []
    for name in sources:
        fetcher = SOURCE_FETCHERS.get(name)
        if fetcher is None:
            logging.warning("Unknown signal source: %s", name)
            continue
        try:
            signal = fetcher(ticker, speculative)
            if signal is not None:
                signals.append(signal)
        except Exception as ex:
            logging.warning("Signal source %s failed for %s: %s", name, ticker, ex)
    return signals


def _pick_primary_signal(signals: list[SourceSignal]) -> SourceSignal:
    for preferred in ("yahoo", "nasdaq", "finviz", "cnbc", "barchart"):
        for signal in signals:
            if signal.source == preferred and signal.close is not None:
                return signal
    return signals[0]


def aggregate_source_scores(
    signals: list[SourceSignal],
    source_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    weights = source_weights or DEFAULT_SOURCE_WEIGHTS
    scores = [float(s.score) for s in signals]
    simple_avg = sum(scores) / len(scores)
    weighted_sum = 0.0
    weight_total = 0.0
    for signal in signals:
        weight = float(weights.get(signal.source, 0.5))
        weighted_sum += float(signal.score) * weight
        weight_total += weight
    weighted_avg = weighted_sum / weight_total if weight_total > 0 else simple_avg
    std = statistics.stdev(scores) if len(scores) > 1 else 0.0
    spread = max(scores) - min(scores)
    return {
        "score_weighted": float(weighted_avg),
        "score_simple_avg": float(simple_avg),
        "source_score_std": float(std),
        "source_score_spread": float(spread),
    }


def is_source_disagreement(
    source_score_std: float,
    source_score_spread: float,
    *,
    max_std: float,
    max_spread: float,
) -> bool:
    return source_score_std >= max_std or source_score_spread >= max_spread


def merge_source_signals(
    ticker: str,
    signals: list[SourceSignal],
    *,
    source_weights: dict[str, float] | None = None,
    max_source_score_std: float = DEFAULT_MAX_SOURCE_SCORE_STD,
    max_source_score_spread: float = DEFAULT_MAX_SOURCE_SCORE_SPREAD,
    disagreement_score_penalty: float = DEFAULT_DISAGREEMENT_SCORE_PENALTY,
    exclude_on_source_disagreement: bool = False,
) -> dict[str, Any] | None:
    if not signals:
        return None

    aggregated = aggregate_source_scores(signals, source_weights)
    disagreement = is_source_disagreement(
        aggregated["source_score_std"],
        aggregated["source_score_spread"],
        max_std=max_source_score_std,
        max_spread=max_source_score_spread,
    )
    if disagreement and exclude_on_source_disagreement:
        logging.info(
            "%s: excluded — source disagreement (std=%.2f, spread=%.2f)",
            ticker,
            aggregated["source_score_std"],
            aggregated["source_score_spread"],
        )
        return None

    score = aggregated["score_weighted"]
    if disagreement:
        score *= disagreement_score_penalty
        logging.info(
            "%s: source disagreement penalty applied (std=%.2f, spread=%.2f)",
            ticker,
            aggregated["source_score_std"],
            aggregated["source_score_spread"],
        )

    tags = theme_tags(ticker)
    bonus = float(theme_score_bonus(ticker))
    if bonus:
        score = float(score) + bonus

    primary = _pick_primary_signal(signals)
    source_scores = {s.source: round(s.score, 4) for s in signals}
    avg_vol20 = None
    for name in ("yahoo", "nasdaq"):
        for signal in signals:
            if signal.source == name:
                avg_vol20 = signal.extra.get("avg_vol20")
                if avg_vol20 is not None:
                    break
        if avg_vol20 is not None:
            break

    return {
        "symbol": ticker,
        "close": primary.close,
        "ret_5d": primary.ret_5d or 0.0,
        "ret_5d_pct": primary.ret_5d_pct or 0.0,
        "ret_1d": primary.ret_1d or 0.0,
        "ret_1d_pct": primary.ret_1d_pct or 0.0,
        "ret_2d": primary.ret_2d or 0.0,
        "vol_ratio": primary.vol_ratio or 0.0,
        "atr_pct": primary.atr_pct or 0.0,
        "near_high_pct": primary.near_high_pct or 0.0,
        "breakout_ok": primary.breakout_ok,
        "volume_ok": primary.volume_ok,
        "above_ma20_pct": primary.above_ma20_pct or 0.0,
        "momentum_ok": primary.momentum_ok,
        "down_days_last_3": primary.down_days_last_3,
        "up_days_last_5": primary.up_days_last_5,
        "down_days_last_5": primary.down_days_last_5,
        "range_5d_pct": primary.range_5d_pct or 0.0,
        "zigzag_in_range": primary.zigzag_in_range,
        "pullback_ok": primary.pullback_ok,
        "avg_vol20": avg_vol20,
        "score": float(score),
        "score_technical": float(aggregated["score_weighted"]),
        "theme_tags": tags,
        "theme_score_bonus": bonus,
        "score_simple_avg": aggregated["score_simple_avg"],
        "source_score_std": aggregated["source_score_std"],
        "source_score_spread": aggregated["source_score_spread"],
        "source_disagreement": disagreement,
        "source_scores": source_scores,
        "sources_used": len(signals),
        "sources_list": [SOURCE_LABELS.get(s.source, s.source) for s in signals],
    }


def build_signal_universe(
    tickers: list[str],
    sources: list[str],
    speculative: bool,
    min_sources: int,
    *,
    min_volume_ratio: float,
    min_price_usd: float,
    min_avg_volume_20d: float,
    source_weights: dict[str, float] | None = None,
    max_source_score_std: float = DEFAULT_MAX_SOURCE_SCORE_STD,
    max_source_score_spread: float = DEFAULT_MAX_SOURCE_SCORE_SPREAD,
    disagreement_score_penalty: float = DEFAULT_DISAGREEMENT_SCORE_PENALTY,
    exclude_on_source_disagreement: bool = False,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        signals = fetch_all_source_signals(ticker, sources, speculative)
        if len(signals) < min_sources:
            logging.info(
                "%s: only %d/%d sources responded, skipping",
                ticker,
                len(signals),
                min_sources,
            )
            continue
        merged = merge_source_signals(
            ticker,
            signals,
            source_weights=source_weights,
            max_source_score_std=max_source_score_std,
            max_source_score_spread=max_source_score_spread,
            disagreement_score_penalty=disagreement_score_penalty,
            exclude_on_source_disagreement=exclude_on_source_disagreement,
        )
        if merged is None:
            continue

        close = float(merged.get("close") or 0.0)
        vol_ratio = float(merged.get("vol_ratio") or 0.0)
        avg_vol20 = merged.get("avg_vol20")
        liquid_ok = close >= min_price_usd
        if avg_vol20 is not None:
            liquid_ok = liquid_ok and float(avg_vol20) >= min_avg_volume_20d
        if not liquid_ok:
            continue

        if speculative:
            vol_ratio = float(merged.get("vol_ratio") or 0.0)
            volume_ok = vol_ratio >= min_volume_ratio
            merged["volume_ok"] = volume_ok
            breakout_ok = bool(merged.get("breakout_ok"))
            if not (volume_ok or breakout_ok):
                continue
        else:
            momentum_ok = bool(merged.get("momentum_ok"))
            volume_ok = vol_ratio >= min_volume_ratio
            if not (momentum_ok or volume_ok):
                continue
            merged["volume_ok"] = volume_ok

        rows.append(merged)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("score", ascending=False)
