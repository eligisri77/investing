"""Block re-entry to symbols after a losing exit."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

# 3x sector / index ETFs — limit overlap in one portfolio.
LEVERAGED_ETF_SYMBOLS = frozenset(
    {
        "TQQQ",
        "SQQQ",
        "SOXL",
        "SOXS",
        "LABU",
        "LABD",
        "TECL",
        "TECS",
        "TNA",
        "TZA",
        "SPXL",
        "SPXS",
        "UPRO",
        "SPXU",
    }
)


def leveraged_symbols(symbols: set[str] | list[str]) -> set[str]:
    return {str(s).upper() for s in symbols if str(s).upper() in LEVERAGED_ETF_SYMBOLS}


def cooldown_until(state: dict[str, Any], symbol: str) -> date | None:
    raw = (state.get("symbol_cooldowns") or {}).get(str(symbol).upper())
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def is_symbol_in_cooldown(state: dict[str, Any], symbol: str, *, as_of: date | None = None) -> bool:
    as_of = as_of or date.today()
    until = cooldown_until(state, symbol)
    return until is not None and as_of <= until


def symbols_in_cooldown(state: dict[str, Any], *, as_of: date | None = None) -> set[str]:
    as_of = as_of or date.today()
    blocked: set[str] = set()
    for symbol in (state.get("symbol_cooldowns") or {}):
        if is_symbol_in_cooldown(state, symbol, as_of=as_of):
            blocked.add(str(symbol).upper())
    return blocked


def record_symbol_cooldown(
    state: dict[str, Any],
    symbol: str,
    *,
    days: int,
    as_of: date | None = None,
    reason: str = "",
) -> None:
    if days <= 0:
        return
    as_of = as_of or date.today()
    until = as_of + timedelta(days=days)
    symbol = str(symbol).upper()
    cooldowns: dict[str, str] = state.setdefault("symbol_cooldowns", {})
    cooldowns[symbol] = until.isoformat()
    logging.info(
        "Symbol cooldown %s until %s (%s)",
        symbol,
        until.isoformat(),
        reason or "loss exit",
    )


def maybe_record_loss_cooldown(
    state: dict[str, Any],
    trade: dict[str, Any],
    cfg: Any,
    *,
    as_of: date | None = None,
) -> None:
    """After a closed trade, block the symbol if it was a loss."""
    days = int(getattr(cfg, "symbol_cooldown_days_after_loss", 0) or 0)
    if days <= 0:
        return
    pnl = float(trade.get("pnl_usd", 0))
    reason = str(trade.get("exit_reason", ""))
    if pnl >= 0 and reason not in {"stop_loss", "floor_price"}:
        return
    if pnl >= 0:
        return
    symbol = str(trade.get("symbol", "")).upper()
    if not symbol:
        return
    record_symbol_cooldown(
        state,
        symbol,
        days=days,
        as_of=as_of,
        reason=f"loss ${pnl:.2f} ({reason})",
    )


def prune_expired_cooldowns(state: dict[str, Any], *, as_of: date | None = None) -> None:
    as_of = as_of or date.today()
    cooldowns = state.get("symbol_cooldowns") or {}
    for symbol, until_str in list(cooldowns.items()):
        try:
            if date.fromisoformat(until_str) < as_of:
                del cooldowns[symbol]
        except ValueError:
            del cooldowns[symbol]


def filter_candidates_dataframe(
    candidates: pd.DataFrame,
    state: dict[str, Any],
    cfg: Any,
    *,
    held_symbols: set[str] | None = None,
    as_of: date | None = None,
    stats_out: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Apply cooldown, min score, and leveraged-ETF cap filters."""
    if candidates is None or candidates.empty:
        return candidates

    as_of = as_of or date.today()
    prune_expired_cooldowns(state, as_of=as_of)
    held = {str(s).upper() for s in (held_symbols or set())}

    min_score = float(getattr(cfg, "min_entry_score", 0) or 0)
    if min_score > 0 and "score" in candidates.columns:
        before = len(candidates)
        below = candidates[candidates["score"] < min_score]
        if stats_out is not None and not below.empty:
            top = below.nlargest(3, "score")
            stats_out["top_skipped_scores"] = [
                {"symbol": str(row["symbol"]), "score": round(float(row["score"]), 2)}
                for _, row in top.iterrows()
            ]
        candidates = candidates[candidates["score"] >= min_score].copy()
        dropped = before - len(candidates)
        if dropped:
            logging.info("Quality filter: dropped %d below min_entry_score %.1f", dropped, min_score)
            if stats_out is not None:
                stats_out["dropped_below_min_score"] = dropped

    blocked = symbols_in_cooldown(state, as_of=as_of)
    if blocked and "symbol" in candidates.columns:
        mask = candidates["symbol"].astype(str).str.upper().isin(blocked)
        skipped_names = candidates.loc[mask, "symbol"].astype(str).tolist()
        candidates = candidates[~mask].copy()
        if skipped_names:
            logging.info("Cooldown filter: skipped %s", ", ".join(sorted(set(skipped_names))))

    max_lev = int(getattr(cfg, "max_leveraged_etf_positions", 0) or 0)
    if max_lev > 0:
        held_lev = leveraged_symbols(held)
        open_lev_count = len(held_lev)
        if open_lev_count >= max_lev:
            lev_in_candidates = candidates["symbol"].isin(LEVERAGED_ETF_SYMBOLS)
            if lev_in_candidates.any():
                names = candidates.loc[lev_in_candidates, "symbol"].tolist()
                candidates = candidates[~lev_in_candidates].copy()
                logging.info(
                    "Leveraged ETF cap (%d): skipped %s",
                    max_lev,
                    ", ".join(names),
                )
        elif open_lev_count == 0:
            lev_rows = candidates[candidates["symbol"].isin(LEVERAGED_ETF_SYMBOLS)]
            if len(lev_rows) > 1:
                keep_symbol = lev_rows.iloc[0]["symbol"]
                drop = (candidates["symbol"].isin(LEVERAGED_ETF_SYMBOLS)) & (
                    candidates["symbol"] != keep_symbol
                )
                dropped = candidates.loc[drop, "symbol"].tolist()
                candidates = candidates[~drop].copy()
                if dropped:
                    logging.info(
                        "Leveraged ETF cap: one per plan — kept %s, skipped %s",
                        keep_symbol,
                        ", ".join(dropped),
                    )

    return candidates
