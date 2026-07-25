"""Hebrew labels for entry strategies (score vs candle methods)."""

from __future__ import annotations

import html
from typing import Any

# Isolate LTR fragments inside RTL Telegram messages (prevents flipped parentheses).
_LRM = "\u200e"


def _ltr(text: str) -> str:
    """Mark a short Latin/number fragment as left-to-right."""
    t = str(text).strip()
    if not t:
        return ""
    return f"{_LRM}{t}{_LRM}"


def strategy_label(obj: dict[str, Any] | None) -> str:
    """Short Hebrew tag for candle / method2 entries. Empty for unknown."""
    if not obj:
        return ""
    strat = str(obj.get("strategy_id") or obj.get("strategy") or "")
    if strat == "method2":
        trig = str(obj.get("trigger") or "").strip()
        side = str(obj.get("side") or "LONG").upper()
        parts = ["נרות סיניים 2"]
        if trig:
            parts.append(_ltr(trig))
        if side == "SHORT":
            parts.append("שורט")
        return " · ".join(parts)
    if strat in {"rising_three", "rising_three_methods"}:
        weak = " · חלש" if obj.get("pattern_weak") else ""
        return f"נרות Rising Three{weak}"
    if strat in {"score", "score_momentum"}:
        return "מומנטום וציון"
    if strat == "trend_pullback":
        return "תיקון במגמה · ניסיוני"
    if strat == "vcp_breakout":
        return "VCP · התכווצות ופריצה · ניסיוני"
    if strat == "relative_strength":
        # Avoid "מול SPY" inside RTL — SPY flipped the parentheses in Telegram.
        return "חוזק יחסי · ניסיוני"
    return ""


def strategy_method_line(obj: dict[str, Any] | None) -> str:
    """User-facing entry-method line, e.g. «שיטת כניסה · מומנטום וציון»."""
    label = strategy_label(obj)
    if not label:
        return ""
    if label.startswith("שיטת כניסה"):
        return label
    return f"שיטת כניסה · {label}"


def strategy_suffix_html(obj: dict[str, Any] | None) -> str:
    """HTML fragment appended after a symbol name.

    No ASCII parentheses — in RTL Telegram they reverse and scramble mixed Hebrew/English.
    """
    line = strategy_method_line(obj)
    if not line:
        return ""
    return f" <i>· {html.escape(line)}</i>"


def strategy_suffix_plain(obj: dict[str, Any] | None) -> str:
    line = strategy_method_line(obj)
    return f" · {line}" if line else ""


def is_candle_strategy(obj: dict[str, Any] | None) -> bool:
    strat = str((obj or {}).get("strategy_id") or (obj or {}).get("strategy") or "")
    return strat in {"method2", "rising_three", "rising_three_methods"}
