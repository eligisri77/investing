"""Broad-market regime filter shared by all entry strategies."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import yfinance as yf


def _close(df: pd.DataFrame) -> pd.Series:
    col = df["Close"]
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]
    return col.astype(float).dropna()


def analyze_market_regime(
    spy: pd.DataFrame,
    qqq: pd.DataFrame,
) -> dict[str, Any]:
    """Return risk_on/neutral/risk_off and an exposure multiplier."""
    details: dict[str, Any] = {}
    votes_above_50 = 0
    both_below_200 = True
    for symbol, df in (("SPY", spy), ("QQQ", qqq)):
        close = _close(df)
        if len(close) < 200:
            return {
                "status": "unknown",
                "exposure_multiplier": 1.0,
                "reason_he": "מסנן ניסיוני: אין מספיק היסטוריה; החשיפה לא שונתה",
                "details": {},
            }
        last = float(close.iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        above50 = last > ma50
        above200 = last > ma200
        votes_above_50 += int(above50)
        both_below_200 = both_below_200 and not above200
        details[symbol] = {
            "close": round(last, 2),
            "ma50": round(ma50, 2),
            "ma200": round(ma200, 2),
            "above_ma50": above50,
            "above_ma200": above200,
        }
    if both_below_200:
        return {
            "status": "risk_off",
            "exposure_multiplier": 0.0,
            "reason_he": "מסנן ניסיוני: SPY ו־QQQ מתחת לממוצע 200; כניסות חדשות נעצרו",
            "details": details,
        }
    if votes_above_50 == 0:
        return {
            "status": "cautious",
            "exposure_multiplier": 0.5,
            "reason_he": "מסנן ניסיוני: SPY ו־QQQ מתחת לממוצע 50; כניסות חדשות הופחתו ל־50%",
            "details": details,
        }
    if votes_above_50 == 1:
        return {
            "status": "neutral",
            "exposure_multiplier": 0.75,
            "reason_he": "מסנן ניסיוני: רק מדד אחד מעל ממוצע 50; כניסות חדשות הופחתו ל־75%",
            "details": details,
        }
    return {
        "status": "risk_on",
        "exposure_multiplier": 1.0,
        "reason_he": "מסנן ניסיוני: SPY ו־QQQ מעל ממוצע 50; החשיפה לא צומצמה",
        "details": details,
    }


def fetch_market_regime() -> dict[str, Any]:
    try:
        frames = yf.download(
            ["SPY", "QQQ"],
            period="2y",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
            group_by="ticker",
        )
        if isinstance(frames.columns, pd.MultiIndex):
            spy = frames["SPY"]
            qqq = frames["QQQ"]
        else:
            raise ValueError("multi-ticker market data missing")
        return analyze_market_regime(spy, qqq)
    except Exception as ex:
        logging.warning("Market regime unavailable: %s", ex)
        return {
            "status": "unknown",
            "exposure_multiplier": 1.0,
            "reason_he": "מסנן ניסיוני: בדיקת השוק נכשלה; החשיפה לא שונתה",
            "details": {},
        }
