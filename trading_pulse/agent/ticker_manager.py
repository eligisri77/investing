"""Manage watchlist tickers in config.json + optional discovery scan."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yfinance as yf

from trading_pulse.core.app_paths import CONFIG_FILE

SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-^]{0,9}$")

# Extra candidates for discovery (not necessarily in the user's list)
DISCOVERY_POOL: list[str] = [
    "NVDL",
    "TSLL",
    "BITX",
    "ETHU",
    "ARKK",
    "SNAP",
    "UBER",
    "SNOW",
    "NET",
    "CRWD",
    "DDOG",
    "PANW",
    "MU",
    "AVGO",
    "ARM",
    "CELH",
    "CELZ",
    "APP",
    "DUOL",
    "CVNA",
    "CAR",
    "AFRM",
    "PATH",
    "AI",
    "BBAI",
    "LCID",
    "NIO",
    "XPEV",
    "DKNG",
    "PENN",
    "FUBO",
    "RBLX",
    "U",
    "MRVL",
    "ON",
    "SMH",
    "SOXS",
    "TNA",
    "TZA",
    "UVXY",
    "VXX",
    "BITO",
    "ETHE",
    "GBTC",
    "CLSK",
    "HUT",
    "WULF",
    "BITF",
    "ACHR",
    "JOBY",
    "LUNR",
    "ASTS",
    "LMT",
    "NOC",
    "SPCE",
    "DNA",
    "BEAM",
    "NTLA",
    "CRSP",
    "EDIT",
    "MRNA",
    "BNTX",
    "XBI",
    "LABD",
    "FNGU",
    "WEBL",
    "NAIL",
    "DFEN",
]


def _read_config() -> dict[str, Any]:
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_config(cfg: dict[str, Any]) -> None:
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")


def normalize_symbol(raw: str) -> str:
    sym = str(raw).strip().upper().replace("$", "")
    if not SYMBOL_RE.fullmatch(sym):
        raise ValueError(f"סימבול לא תקין: {raw}")
    return sym


def list_tickers() -> list[str]:
    cfg = _read_config()
    return list(cfg.get("tickers") or [])


def ticker_exists_on_market(symbol: str) -> bool:
    try:
        df = yf.download(
            symbol,
            period="5d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        return df is not None and not df.empty
    except Exception as ex:
        logging.warning("Ticker validation failed for %s: %s", symbol, ex)
        return False


def add_ticker(symbol: str, *, validate: bool = True) -> dict[str, Any]:
    sym = normalize_symbol(symbol)
    cfg = _read_config()
    tickers: list[str] = list(cfg.get("tickers") or [])
    if sym in tickers:
        return {"ok": False, "symbol": sym, "reason": "already_in_list", "tickers": tickers}
    if validate and not ticker_exists_on_market(sym):
        return {"ok": False, "symbol": sym, "reason": "not_found", "tickers": tickers}
    tickers.append(sym)
    cfg["tickers"] = tickers
    _write_config(cfg)
    logging.info("Added ticker %s to watchlist (%d total)", sym, len(tickers))
    return {"ok": True, "symbol": sym, "tickers": tickers}


def remove_ticker(symbol: str) -> dict[str, Any]:
    sym = normalize_symbol(symbol)
    cfg = _read_config()
    tickers: list[str] = list(cfg.get("tickers") or [])
    if sym not in tickers:
        return {"ok": False, "symbol": sym, "reason": "not_in_list", "tickers": tickers}
    tickers = [t for t in tickers if t != sym]
    cfg["tickers"] = tickers
    _write_config(cfg)
    logging.info("Removed ticker %s from watchlist (%d total)", sym, len(tickers))
    return {"ok": True, "symbol": sym, "tickers": tickers}


def discover_tickers(cfg: Any, *, max_add: int = 3, max_scan: int = 35) -> list[dict[str, Any]]:
    """Scan candidate pool and return top scorers not already in the watchlist."""
    from trading_pulse.agent.dryrun_agent import fetch_signal_universe, is_speculative

    current = set(list_tickers())
    candidates = [s for s in DISCOVERY_POOL if s not in current]
    if not candidates:
        return []

    scan_list = candidates[:max_scan]
    logging.info("Discovering tickers: scanning %d candidates", len(scan_list))
    df = fetch_signal_universe(scan_list, cfg)
    if df.empty:
        return []

    found: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        sym = str(row["symbol"])
        if sym in current:
            continue
        found.append(
            {
                "symbol": sym,
                "score": round(float(row["score"]), 2),
                "ret_5d_pct": round(float(row.get("ret_5d_pct", 0)), 2),
                "atr_pct": round(float(row.get("atr_pct", 0)), 2) if is_speculative(cfg) else None,
            }
        )
        if len(found) >= max_add:
            break
    return found


def discover_and_add_tickers(cfg: Any, *, max_add: int = 3) -> dict[str, Any]:
    picks = discover_tickers(cfg, max_add=max_add)
    added: list[dict[str, Any]] = []
    skipped: list[str] = []
    for pick in picks:
        result = add_ticker(pick["symbol"], validate=False)
        if result["ok"]:
            added.append({**pick, "tickers": result["tickers"]})
        else:
            skipped.append(pick["symbol"])
    return {
        "added": added,
        "skipped": skipped,
        "tickers": list_tickers(),
    }


def format_tickers_list_html() -> str:
    from trading_pulse.telegram.telegram_format import escape_html

    tickers = list_tickers()
    if not tickers:
        return "<b>📋 רשימת מניות</b>\nריקה."
    lines = [
        f"<b>📋 רשימת מניות ({len(tickers)})</b>",
        "",
        escape_html(", ".join(tickers)),
        "",
        "<b>פקודות:</b>",
        "<code>הוסף SMCI</code> · <code>הסר IONQ</code>",
        "<code>חפש מניות</code> — סריקה והוספה אוטומטית",
    ]
    return "\n".join(lines)


def format_add_ticker_reply(result: dict[str, Any]) -> str:
    from trading_pulse.telegram.telegram_format import escape_html

    sym = escape_html(result["symbol"])
    if result["ok"]:
        n = len(result["tickers"])
        return f"✅ <b>{sym}</b> נוספה לרשימה ({n} מניות בסך הכל)."
    if result.get("reason") == "already_in_list":
        return f"ℹ️ <b>{sym}</b> כבר ברשימה."
    if result.get("reason") == "not_found":
        return f"❌ לא מצאתי מניה <b>{sym}</b> — בדוק את הסימבול."
    return f"❌ לא ניתן להוסיף <b>{sym}</b>."


def format_remove_ticker_reply(result: dict[str, Any]) -> str:
    from trading_pulse.telegram.telegram_format import escape_html

    sym = escape_html(result["symbol"])
    if result["ok"]:
        n = len(result["tickers"])
        return f"✅ <b>{sym}</b> הוסרה מהרשימה ({n} נשארו)."
    if result.get("reason") == "not_in_list":
        return f"ℹ️ <b>{sym}</b> לא הייתה ברשימה."
    return f"❌ לא ניתן להסיר <b>{sym}</b>."


def format_discover_reply(result: dict[str, Any]) -> str:
    from trading_pulse.telegram.telegram_format import escape_html

    added = result.get("added") or []
    lines = ["<b>🔍 סריקת מניות</b>", ""]
    if not added:
        lines.append("לא נמצאו מניות חדשות מתאימות להוספה.")
        lines.append(f"ברשימה: {len(result.get('tickers') or [])} מניות.")
        return "\n".join(lines)
    lines.append(f"<b>נוספו {len(added)} מניות:</b>")
    for item in added:
        extra = f" · ציון {item['score']}"
        if item.get("ret_5d_pct") is not None:
            extra += f" · 5d {item['ret_5d_pct']:+.1f}%"
        lines.append(f"• <b>{escape_html(item['symbol'])}</b>{escape_html(extra)}")
    lines.extend(
        [
            "",
            f"סה\"כ ברשימה: {len(result.get('tickers') or [])} מניות",
            "המניות החדשות ייכנסו לתוכנית הבאה.",
        ]
    )
    return "\n".join(lines)
