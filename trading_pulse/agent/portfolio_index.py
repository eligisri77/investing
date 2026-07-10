"""Numbered portfolio slots for Telegram trade commands."""

from __future__ import annotations

from typing import Any


def list_numbered_holdings() -> list[dict[str, Any]]:
    """Holdings with stable slot numbers (1..n) by entry order."""
    from trading_pulse.agent.portfolio import build_portfolio

    pdata = build_portfolio()
    holding = [p for p in pdata.get("open_positions", []) if p.get("status") == "holding"]
    out: list[dict[str, Any]] = []
    for idx, pos in enumerate(holding, start=1):
        row = dict(pos)
        row["slot"] = idx
        out.append(row)
    return out


def slot_to_symbol(slot: int) -> str | None:
    if slot < 1:
        return None
    holdings = list_numbered_holdings()
    if slot > len(holdings):
        return None
    return str(holdings[slot - 1]["symbol"])


def symbol_to_slot(symbol: str) -> int | None:
    symbol = symbol.upper()
    for row in list_numbered_holdings():
        if str(row["symbol"]) == symbol:
            return int(row["slot"])
    return None


def resolve_trade_target(ref: str) -> str | None:
    """Map slot number or ticker symbol to a held symbol."""
    ref = ref.strip()
    if ref.isdigit():
        return slot_to_symbol(int(ref))
    sym = ref.upper()
    if symbol_to_slot(sym) is not None:
        return sym
    return sym if sym else None


def attach_slots_to_portfolio(data: dict[str, Any]) -> dict[str, Any]:
    """Add slot field to holding rows in portfolio payload (for images/text)."""
    slot = 0
    positions: list[dict[str, Any]] = []
    for pos in data.get("open_positions") or []:
        row = dict(pos)
        if row.get("status") == "holding":
            slot += 1
            row["slot"] = slot
        positions.append(row)
    return {**data, "open_positions": positions}
