"""Hourly intraday checks on held positions and rising watchlist candidates."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

import pandas as pd
import yfinance as yf

AlertKind = Literal[
    "floor_breach",
    "near_stop",
    "heavy_loss",
    "intraday_drop",
    "near_take_profit",
    "strong_gain",
    "volume_spike_down",
]

ActionKind = Literal["buy", "swap", "watch", "sell"]

NEAR_STOP_BUFFER = 0.02
INTRADAY_DROP_WARN = 0.04
INTRADAY_RISE_STRONG = 0.05
SWAP_SCORE_GAP = 3.0
MIN_CANDIDATE_SCORE = 8.0
DEFAULT_COOLDOWN_MINUTES = 120


@dataclass
class PositionAlert:
    symbol: str
    kind: AlertKind
    message: str
    severity: int = 1


@dataclass
class TradeSuggestion:
    kind: ActionKind
    symbol: str
    message: str
    score: float = 0.0
    swap_from: str | None = None
    # Idle-cash deploy offer — may repeat every check interval (not the long alert cooldown).
    cash_deploy: bool = False


@dataclass
class IntradayReport:
    checked_at: str
    holdings: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[PositionAlert] = field(default_factory=list)
    suggestions: list[TradeSuggestion] = field(default_factory=list)
    floor_sells: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        return bool(self.alerts or self.suggestions or self.floor_sells)


def parse_hhmm(hhmm: str) -> tuple[int, int]:
    hour, minute = (int(x) for x in str(hhmm).split(":", 1))
    return hour, minute


def is_within_market_hours(cfg: Any, *, now: datetime | None = None) -> bool:
    """True during configured market window (open…close times are UTC in config)."""
    from datetime import timezone

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now_utc = now.replace(tzinfo=timezone.utc)
    else:
        now_utc = now.astimezone(timezone.utc)
    open_h, open_m = parse_hhmm(str(getattr(cfg, "market_open_sim_time", "13:30")))
    close_h, close_m = parse_hhmm(str(getattr(cfg, "market_close_sim_time", "20:20")))
    start = now_utc.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    end = now_utc.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    return start <= now_utc <= end


def _extract_series(df: pd.DataFrame, col: str) -> pd.Series:
    series = df[col]
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    return series


def fetch_intraday_quote(symbol: str) -> dict[str, float] | None:
    """Latest price and today's session stats when market data is available."""
    try:
        df = yf.download(
            symbol,
            period="1d",
            interval="5m",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            df = yf.download(
                symbol,
                period="5d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            ).dropna()
            if df.empty:
                return None
            last_row = df.iloc[-1]
            close = float(_extract_series(df, "Close").iloc[-1])
            open_px = float(_extract_series(df, "Open").iloc[-1])
            high = float(_extract_series(df, "High").iloc[-1])
            low = float(_extract_series(df, "Low").iloc[-1])
        else:
            close = float(_extract_series(df, "Close").iloc[-1])
            open_px = float(_extract_series(df, "Open").iloc[0])
            high = float(_extract_series(df, "High").max())
            low = float(_extract_series(df, "Low").min())

        if close <= 0 or open_px <= 0:
            return None
        return {
            "last": close,
            "open": open_px,
            "high": high,
            "low": low,
            "change_pct": round((close / open_px - 1) * 100, 2),
            "day_change_pct": round((close / open_px - 1) * 100, 2),
        }
    except Exception as ex:
        logging.warning("Intraday quote failed for %s: %s", symbol, ex)
        return None


def analyze_position(
    pos: dict[str, Any],
    quote: dict[str, float],
    cfg: Any,
) -> list[PositionAlert]:
    from trading_pulse.agent.positions import position_floor_price

    symbol = str(pos["symbol"])
    entry = float(pos.get("entry_price") or pos.get("entry_ref_price") or 0)
    if entry <= 0:
        return []

    last = float(quote["last"])
    floor = position_floor_price(pos, cfg, entry=entry)
    pnl_pct = (last / entry - 1) * 100
    sl_pct = float(pos.get("stop_loss_pct", getattr(cfg, "stop_loss_pct", 0.12)))
    tp_pct = float(pos.get("take_profit_pct", getattr(cfg, "take_profit_pct", 0.25)))
    take_price = entry * (1 + tp_pct)
    dist_floor_pct = (last / floor - 1) * 100 if floor > 0 else 0
    dist_tp_pct = (take_price / last - 1) * 100
    intraday_pct = float(quote.get("change_pct", 0))

    alerts: list[PositionAlert] = []

    if last <= floor:
        alerts.append(
            PositionAlert(
                symbol,
                "floor_breach",
                f"מתחת למחיר תחתון ${floor:.2f} (${last:.2f}) · מכירה אוטומטית",
                severity=3,
            )
        )
        return alerts

    if dist_floor_pct <= NEAR_STOP_BUFFER * 100:
        alerts.append(
            PositionAlert(
                symbol,
                "near_stop",
                f"קרוב למחיר תחתון (${floor:.2f}, עוד {dist_floor_pct:+.1f}%) · {pnl_pct:+.1f}% מהכניסה",
                severity=3,
            )
        )
    elif pnl_pct <= -(sl_pct * 100 * 0.65):
        alerts.append(
            PositionAlert(
                symbol,
                "heavy_loss",
                f"הפסד משמעותי {pnl_pct:+.1f}% · שקול יציאה מוקדמת",
                severity=2,
            )
        )

    if intraday_pct <= -INTRADAY_DROP_WARN * 100:
        alerts.append(
            PositionAlert(
                symbol,
                "intraday_drop",
                f"ירידה יומית {intraday_pct:+.1f}% מהפתיחה",
                severity=2,
            )
        )

    if dist_tp_pct <= NEAR_STOP_BUFFER * 100:
        alerts.append(
            PositionAlert(
                symbol,
                "near_take_profit",
                f"קרוב ליעד רווח ({dist_tp_pct:.1f}% ל-TP) · {pnl_pct:+.1f}%",
                severity=1,
            )
        )
    elif intraday_pct >= INTRADAY_RISE_STRONG * 100:
        alerts.append(
            PositionAlert(
                symbol,
                "strong_gain",
                f"עלייה חזקה היום {intraday_pct:+.1f}% · {pnl_pct:+.1f}% מהכניסה",
                severity=1,
            )
        )

    return alerts


def _score_map(universe: pd.DataFrame) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if universe is None or universe.empty:
        return rows
    for _, row in universe.iterrows():
        sym = str(row["symbol"])
        rows[sym] = {
            "score": float(row.get("score", 0)),
            "ret_5d_pct": float(row.get("ret_5d_pct", 0) or 0),
            "vol_ratio": float(row.get("vol_ratio", 0) or 0),
            "volume_ok": bool(row.get("volume_ok", False)),
            "close": float(row.get("close", 0) or 0),
        }
    return rows


SELL_STRONG_DROP_PCT = -7.0


def _plan_sell_or_cooldown_symbols(
    cfg: Any,
    state: dict[str, Any] | None,
) -> set[str]:
    """Symbols we should not suggest buying mid-day (plan sell / cooldown / recent exit)."""
    skip: set[str] = set()
    try:
        from trading_pulse.agent.plan_engine import active_trading_day
        from trading_pulse.agent.dryrun_agent import plan_path, read_json

        day = active_trading_day()
        if day:
            path = plan_path(date.fromisoformat(day))
            if path.exists():
                plan = read_json(path)
                for action in plan.get("holding_actions") or []:
                    if str(action.get("verdict")) in {"sell", "take_profit", "swap"}:
                        sym = str(action.get("symbol") or "").upper()
                        if sym:
                            skip.add(sym)
        if state is not None:
            from trading_pulse.agent.symbol_cooldown import symbols_in_cooldown

            skip |= {s.upper() for s in symbols_in_cooldown(state)}
            from trading_pulse.core.schedule_tz import us_trading_session_date

            today = us_trading_session_date().isoformat()
            for trade in state.get("history") or []:
                if str(trade.get("exit_day") or trade.get("day") or "") == today:
                    sym = str(trade.get("symbol") or "").upper()
                    if sym:
                        skip.add(sym)
            for trade in state.get("intraday_floor_exits") or []:
                if str(trade.get("exit_day") or trade.get("day") or "") == today:
                    sym = str(trade.get("symbol") or "").upper()
                    if sym:
                        skip.add(sym)
    except Exception as ex:
        logging.debug("Intraday buy-skip set failed: %s", ex)
    return skip


def _is_rising(cfg: Any, data: dict[str, Any]) -> bool:
    return (
        float(data.get("ret_5d_pct", 0)) > 2
        or bool(data.get("volume_ok"))
        or float(data.get("vol_ratio", 0)) >= float(getattr(cfg, "min_volume_ratio", 1.0))
    )


def _top_candidate(
    cfg: Any,
    scores: dict[str, dict[str, Any]],
    skip: set[str] | frozenset[str],
) -> tuple[str, dict[str, Any]] | None:
    """Best rising, high-scored symbol not already held/pending."""
    candidates = [
        (sym, data)
        for sym, data in scores.items()
        if sym not in skip and float(data.get("score", 0)) >= MIN_CANDIDATE_SCORE
    ]
    candidates.sort(key=lambda x: -x[1]["score"])
    for sym, data in candidates:
        if _is_rising(cfg, data):
            return sym, data
    return None


def _sell_recommendations(
    cfg: Any,
    holdings: list[dict[str, Any]],
    quotes: dict[str, dict[str, float]],
    alerts_by_symbol: dict[str, list[PositionAlert]],
    scores: dict[str, dict[str, Any]],
    skip: set[str] | frozenset[str],
) -> list[TradeSuggestion]:
    """Explicit 'sell now' advice when a holding is crashing, incl. what to do
    with the freed-up cash (rotate into a strong pick, or hold cash)."""
    out: list[TradeSuggestion] = []
    for h in holdings:
        sym = str(h["symbol"])
        h_alerts = alerts_by_symbol.get(sym, [])
        kinds = {a.kind for a in h_alerts}
        day_pct = float(quotes.get(sym, {}).get("change_pct", 0))
        crashing = bool(kinds & {"near_stop", "heavy_loss", "floor_breach"}) or (
            "intraday_drop" in kinds and day_pct <= SELL_STRONG_DROP_PCT
        )
        if not crashing:
            continue
        entry = float(h.get("entry_price") or h.get("entry_ref_price") or 0)
        last = float(quotes.get(sym, {}).get("last", 0))
        pnl_pct = (last / entry - 1) * 100 if entry > 0 and last > 0 else 0
        # Avoid "+/-" signs inside Hebrew text — RTL scrambles them ("‎-9.0%").
        if entry > 0 and last > 0:
            if pnl_pct <= -0.05:
                pnl_phrase = f"המניה ירדה {abs(pnl_pct):.1f}% מאז הקנייה"
            elif pnl_pct >= 0.05:
                pnl_phrase = f"המניה עלתה {pnl_pct:.1f}% מאז הקנייה"
            else:
                pnl_phrase = "המניה סביב מחיר הקנייה"
        else:
            pnl_phrase = ""
        if kinds & {"near_stop", "floor_breach"}:
            reason = "המחיר קרוב לרף המכירה"
        elif "heavy_loss" in kinds or (
            "intraday_drop" in kinds and day_pct <= SELL_STRONG_DROP_PCT
        ):
            reason = "ירידה חדה היום"
        else:
            reason = "אזהרת מכירה"
        why = f"{reason}" + (f" — {pnl_phrase}" if pnl_phrase else "")

        replacement = _top_candidate(cfg, scores, set(skip) | {sym})
        if replacement is not None:
            to_sym, to_data = replacement
            sold_usd = float(h.get("capital_usd", 0))
            out.append(
                TradeSuggestion(
                    kind="swap",
                    symbol=to_sym,
                    score=float(to_data.get("score", 0)),
                    swap_from=sym,
                    message=(
                        f"{why}. ההצעה: למכור ${sold_usd:.0f} מ-{sym} "
                        f"ולקנות במקומה {to_sym} (ציון {float(to_data.get('score', 0)):.1f})"
                    ),
                )
            )
        else:
            out.append(
                TradeSuggestion(
                    kind="sell",
                    symbol=sym,
                    message=(
                        f"{why}. אין כרגע מניה חזקה להחלפה, "
                        f"לכן ההצעה: למכור את {sym} ולשמור את הכסף במזומן להזדמנות הבאה"
                    ),
                )
            )
    return out


def _free_cash_usd(cfg: Any, state: dict[str, Any] | None, holdings: list[dict[str, Any]]) -> float:
    from trading_pulse.agent.positions import available_capital

    state_obj = state or {"equity": 0, "open_positions": holdings}
    return float(available_capital(cfg, state_obj))


def _min_cash_deploy_usd(cfg: Any) -> float:
    return float(getattr(cfg, "intraday_cash_topup_min_usd", 20.0) or 20.0)


def _append_idle_cash_topup(
    cfg: Any,
    holdings: list[dict[str, Any]],
    scores: dict[str, dict[str, Any]],
    state: dict[str, Any] | None,
    exclude_symbols: set[str],
    suggestions: list[TradeSuggestion],
    *,
    cash: float | None = None,
) -> None:
    """Cash sits idle — offer to top up the strongest holding.

    Used when the book is full, or when there is cash but no new-buy candidate
    this hour. `exclude_symbols` are holdings flagged for sell/swap/cooldown.
    """
    if not holdings:
        return
    if cash is None:
        cash = _free_cash_usd(cfg, state, holdings)
    min_cash = _min_cash_deploy_usd(cfg)
    if cash < min_cash:
        return
    candidates = [h for h in holdings if str(h.get("symbol")) not in exclude_symbols]
    if not candidates:
        return
    best_held = max(
        candidates,
        key=lambda h: float(scores.get(str(h.get("symbol")), {}).get("score", 0)),
    )
    sym = str(best_held.get("symbol"))
    score = float(scores.get(sym, {}).get("score", 0))
    suggestions.append(
        TradeSuggestion(
            kind="buy",
            symbol=sym,
            score=score,
            cash_deploy=True,
            message=(
                f"יש ${cash:.0f} מזומן פנוי — הצעה לחזק את {sym} "
                f"(ציון {score:.1f}) ב־~${cash:.0f}"
            ),
        )
    )


def build_suggestions(
    cfg: Any,
    holdings: list[dict[str, Any]],
    scores: dict[str, dict[str, Any]],
    quotes: dict[str, dict[str, float]],
    alerts_by_symbol: dict[str, list[PositionAlert]],
    *,
    exclude_symbols: set[str] | frozenset[str] | None = None,
    state: dict[str, Any] | None = None,
) -> list[TradeSuggestion]:
    held = {str(h["symbol"]) for h in holdings}
    skip = held | set(exclude_symbols or ())
    skip |= _plan_sell_or_cooldown_symbols(cfg, state)

    suggestions: list[TradeSuggestion] = _sell_recommendations(
        cfg, holdings, quotes, alerts_by_symbol, scores, skip
    )
    sell_symbols: set[str] = set()
    for s in suggestions:
        if s.kind == "sell":
            sell_symbols.add(s.symbol)
        elif s.kind == "swap" and s.swap_from:
            sell_symbols.add(str(s.swap_from))

    max_open = int(getattr(cfg, "max_open_positions", 4))
    open_slots = max(0, max_open - len(holdings))
    cash = _free_cash_usd(cfg, state, holdings)
    min_cash = _min_cash_deploy_usd(cfg)
    has_deployable_cash = cash >= min_cash
    topup_exclude = sell_symbols | _plan_sell_or_cooldown_symbols(cfg, state)

    if open_slots <= 0:
        _append_idle_cash_topup(
            cfg,
            holdings,
            scores,
            state,
            topup_exclude,
            suggestions,
            cash=cash,
        )

    top = _top_candidate(cfg, scores, skip) if scores else None

    if open_slots > 0 and top is not None:
        best_sym, best = top
        state_obj = state or {"equity": 0, "open_positions": holdings}
        equity = float(state_obj.get("equity", 0)) or cash + sum(
            float(p.get("capital_usd", 0)) for p in holdings
        )
        pos_pct = float(getattr(cfg, "max_position_pct", 0.34))
        if has_deployable_cash:
            buy_usd = round(min(cash, equity * pos_pct), 0)
            suggestions.append(
                TradeSuggestion(
                    kind="buy",
                    symbol=best_sym,
                    score=float(best["score"]),
                    cash_deploy=True,
                    message=(
                        f"יש ${cash:.0f} מזומן — הצעה: {best_sym} "
                        f"(ציון {best['score']:.1f} · 5י {best.get('ret_5d_pct', 0):+.1f}% · "
                        f"נפח {best.get('vol_ratio', 0):.2f}x) ~${buy_usd:.0f}"
                    ),
                )
            )
            return suggestions
        # No idle cash — still surface a strong name (swap/funding path).
        buy_usd = round(equity * pos_pct, 0)
        suggestions.append(
            TradeSuggestion(
                kind="buy",
                symbol=best_sym,
                score=float(best["score"]),
                message=(
                    f"ציון {best['score']:.1f} · 5י {best.get('ret_5d_pct', 0):+.1f}% · "
                    f"נפח {best.get('vol_ratio', 0):.2f}x · מומלץ ~${buy_usd:.0f}"
                ),
            )
        )
        return suggestions

    # Cash free + open slot but no fresh candidate this hour → top up a holding.
    if open_slots > 0 and has_deployable_cash:
        if not any(s.cash_deploy for s in suggestions):
            _append_idle_cash_topup(
                cfg,
                holdings,
                scores,
                state,
                topup_exclude,
                suggestions,
                cash=cash,
            )
        return suggestions

    if top is None:
        return suggestions
    best_sym, best = top

    held_scores = [
        (
            str(h["symbol"]),
            float(scores.get(str(h["symbol"]), {}).get("score", 0)),
            float(quotes.get(str(h["symbol"]), {}).get("change_pct", 0)),
            alerts_by_symbol.get(str(h["symbol"]), []),
        )
        for h in holdings
        if str(h["symbol"]) not in sell_symbols
    ]
    if not held_scores:
        return suggestions

    weakest = min(
        held_scores,
        key=lambda x: (x[1], x[2], sum(a.severity for a in x[3])),
    )
    weak_sym, weak_score, weak_day_pct, weak_alerts = weakest
    score_gap = float(best["score"]) - weak_score
    weak_underperforming = weak_day_pct < 0 or any(
        a.kind in {"near_stop", "heavy_loss", "intraday_drop", "floor_breach"} for a in weak_alerts
    )

    if score_gap >= SWAP_SCORE_GAP and weak_underperforming:
        suggestions.append(
            TradeSuggestion(
                kind="swap",
                symbol=best_sym,
                score=float(best["score"]),
                swap_from=weak_sym,
                message=(
                    f"החלף {weak_sym} (ציון {weak_score:.1f}, היום {weak_day_pct:+.1f}%) "
                    f"ב-{best_sym} (ציון {best['score']:.1f}, 5י {best.get('ret_5d_pct', 0):+.1f}%)"
                ),
            )
        )
    elif score_gap >= SWAP_SCORE_GAP * 0.7:
        suggestions.append(
            TradeSuggestion(
                kind="watch",
                symbol=best_sym,
                score=float(best["score"]),
                message=(
                    f"{best_sym} עולה (ציון {best['score']:.1f}) — עקוב, אולי הזדמנות מחר"
                ),
            )
        )

    return suggestions


def _cooldown_key(symbol: str, kind: str) -> str:
    return f"{symbol}:{kind}"


def filter_cooled_down(
    report: IntradayReport,
    state: dict[str, Any],
    cooldown_minutes: int,
    *,
    cash_deploy_cooldown_minutes: int | None = None,
    now: datetime | None = None,
) -> IntradayReport:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cooldowns: dict[str, str] = state.setdefault("intraday_alert_cooldowns", {})
    cutoff = now - timedelta(minutes=cooldown_minutes)
    cash_cd = (
        int(cash_deploy_cooldown_minutes)
        if cash_deploy_cooldown_minutes is not None
        else cooldown_minutes
    )
    # Allow repeating the same cash offer every check interval (e.g. hourly).
    cash_cutoff = now - timedelta(minutes=max(15, cash_cd))

    def fresh(key: str, *, cutoff_at: datetime) -> bool:
        ts = cooldowns.get(key)
        if not ts:
            return True
        try:
            prev = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            return prev < cutoff_at
        except ValueError:
            return True

    report.alerts = [
        a
        for a in report.alerts
        if fresh(_cooldown_key(a.symbol, a.kind), cutoff_at=cutoff)
    ]
    report.suggestions = [
        s
        for s in report.suggestions
        if fresh(
            _cooldown_key(s.symbol, f"suggest_{s.kind}"),
            cutoff_at=cash_cutoff if s.cash_deploy else cutoff,
        )
    ]
    return report


def mark_cooldowns(report: IntradayReport, state: dict[str, Any], *, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cooldowns: dict[str, str] = state.setdefault("intraday_alert_cooldowns", {})
    iso = now.isoformat()
    for alert in report.alerts:
        cooldowns[_cooldown_key(alert.symbol, alert.kind)] = iso
    for suggestion in report.suggestions:
        cooldowns[_cooldown_key(suggestion.symbol, f"suggest_{suggestion.kind}")] = iso
    # Prune entries older than 2 days
    stale = now - timedelta(days=2)
    for key, ts in list(cooldowns.items()):
        try:
            prev = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            if prev < stale:
                del cooldowns[key]
        except ValueError:
            del cooldowns[key]


def enforce_floor_exits(
    cfg: Any,
    state: dict[str, Any],
    quotes: dict[str, dict[str, float]],
    *,
    trading_day: str | None = None,
) -> list[dict[str, Any]]:
    """Sell open positions immediately when live price is at or below floor."""
    from trading_pulse.agent.positions import (
        backfill_position_floors,
        close_position_at_price,
        ensure_open_positions,
        floor_closed_today,
        position_floor_price,
    )

    ensure_open_positions(state)
    backfill_position_floors(state, cfg)
    day_str = trading_day or date.today().isoformat()
    closed: list[dict[str, Any]] = []

    for pos in list(state.get("open_positions", [])):
        symbol = str(pos["symbol"])
        if floor_closed_today(state, symbol, day_str):
            continue
        quote = quotes.get(symbol)
        if not quote:
            continue
        last = float(quote["last"])
        floor = position_floor_price(pos, cfg)
        if last > floor:
            continue
        trade = close_position_at_price(cfg, state, pos, last, "floor_price", trading_day=day_str)
        closed.append(trade)
        logging.info(
            "Floor exit %s @ $%s (floor $%s) PnL $%s",
            symbol,
            last,
            floor,
            trade.get("pnl_usd"),
        )
    return closed


def build_intraday_report(cfg: Any, state: dict[str, Any]) -> IntradayReport:
    from trading_pulse.agent.portfolio import load_open_positions

    holdings = [
        h
        for h in load_open_positions()
        if h.get("status") in {None, "holding", "pending_execution"}
    ]
    report = IntradayReport(checked_at=datetime.now().astimezone().isoformat())

    held_symbols = {str(h["symbol"]) for h in holdings if h.get("status") == "holding"}
    quotes: dict[str, dict[str, float]] = {}
    for sym in held_symbols:
        q = fetch_intraday_quote(sym)
        if q:
            quotes[sym] = q

    report.floor_sells = enforce_floor_exits(cfg, state, quotes)

    if not holdings and not cfg.tickers and not report.floor_sells:
        return report

    alerts_by_symbol: dict[str, list[PositionAlert]] = {}
    for pos in holdings:
        sym = str(pos["symbol"])
        if pos.get("status") != "holding":
            continue
        if any(s.get("symbol") == sym for s in report.floor_sells):
            continue
        quote = quotes.get(sym)
        if not quote:
            continue
        pos_alerts = analyze_position(pos, quote, cfg)
        if pos_alerts:
            alerts_by_symbol[sym] = pos_alerts
            report.alerts.extend(pos_alerts)
        entry = float(pos.get("entry_price") or pos.get("entry_ref_price") or 0)
        last = float(quote["last"])
        from trading_pulse.agent.positions import position_floor_price

        floor = position_floor_price(pos, cfg, entry=entry) if entry > 0 else None
        report.holdings.append(
            {
                "symbol": sym,
                "last": last,
                "entry": entry,
                "capital_usd": float(pos.get("capital_usd", 0)),
                "floor_price": floor,
                "pnl_pct": round((last / entry - 1) * 100, 2) if entry > 0 else 0,
                "day_change_pct": quote.get("change_pct", 0),
                "status": pos.get("status", "holding"),
                "strategy": pos.get("strategy"),
                "trigger": pos.get("trigger"),
                "side": pos.get("side"),
                "pattern_weak": pos.get("pattern_weak"),
            }
        )

    try:
        from trading_pulse.agent.dryrun_agent import fetch_signal_universe

        scan_tickers = sorted(set(cfg.tickers or []) | held_symbols)
        universe = fetch_signal_universe(scan_tickers, cfg)
        scores = _score_map(universe)
    except Exception as ex:
        logging.warning("Intraday signal scan failed: %s", ex)
        scores = {}

    from trading_pulse.agent.dryrun_agent import pending_plan_entry_symbols

    pending_entries = pending_plan_entry_symbols()
    report.suggestions = build_suggestions(
        cfg,
        [h for h in holdings if h.get("status") == "holding" and h["symbol"] not in {s["symbol"] for s in report.floor_sells}],
        scores,
        quotes,
        alerts_by_symbol,
        exclude_symbols=pending_entries,
        state=state,
    )
    return report


def run_intraday_check(cfg: Any, state: dict[str, Any]) -> bool:
    """Build report, send Telegram if noteworthy. Returns True when a message was sent."""
    from trading_pulse.agent.dryrun_agent import (
        is_us_trading_day,
        plan_path,
        read_json,
        save_json,
        send_entry_notifications,
        send_user_notification,
    )
    from trading_pulse.core.app_paths import STATE_FILE
    from trading_pulse.core.schedule_tz import us_trading_session_date
    from trading_pulse.telegram.telegram_format import (
        format_intraday_monitor,
    )

    today = us_trading_session_date()
    if not is_us_trading_day(today):
        return False
    if not bool(getattr(cfg, "intraday_check_enabled", True)):
        return False
    if not is_within_market_hours(cfg):
        return False

    sent_any = False

    # שיטה 2: fill pending breakouts on daily level or 5m/1m micro trigger
    try:
        from trading_pulse.agent.method2_intraday import try_fill_pending_method2

        path = plan_path(today)
        if path.exists():
            plan = read_json(path)
            m2_fills = try_fill_pending_method2(cfg, state, plan, today)
            if m2_fills:
                save_json(path, plan)
                save_json(STATE_FILE, state)
                send_entry_notifications(
                    cfg,
                    m2_fills,
                    trading_day=today.isoformat(),
                    subtitle="נרות סיניים 2 · פריצה תוך־יומית",
                    context="entry:method2",
                )
                sent_any = True
                logging.info("Method2 intraday: filled %d", len(m2_fills))
    except Exception as ex:
        logging.warning("Method2 intraday fill failed: %s", ex)

    report = build_intraday_report(cfg, state)
    cooldown = int(getattr(cfg, "intraday_alert_cooldown_minutes", DEFAULT_COOLDOWN_MINUTES))
    # Cash-deploy offers follow the check interval so idle cash gets a fresh
    # review + offer about once per hour during the session.
    cash_cd = int(getattr(cfg, "intraday_check_interval_minutes", 60) or 60)
    report = filter_cooled_down(
        report,
        state,
        cooldown,
        cash_deploy_cooldown_minutes=cash_cd,
    )

    if not report.has_content:
        if not sent_any:
            logging.info("Intraday check: nothing noteworthy")
        return sent_any

    text = format_intraday_monitor(report)
    sent = False
    try:
        from trading_pulse.agent.dryrun_agent import send_telegram_photo
        from trading_pulse.telegram.reply_cards import card_intraday_monitor

        img = card_intraday_monitor(report)
        # Short caption only — details live in the PNG squares (RTL-safe).
        sent = send_telegram_photo(
            cfg,
            img,
            "מעקב שעתי",
            context="intraday",
            inbox_text=_strip_for_inbox(text),
        )
    except Exception as ex:
        logging.warning("Intraday card failed, sending text: %s", ex)
        sent = send_user_notification(cfg, text, context="intraday", parse_mode="HTML")
    if sent:
        mark_cooldowns(report, state)
        save_json(STATE_FILE, state)
        logging.info(
            "Intraday alert sent: %d alert(s), %d suggestion(s)",
            len(report.alerts),
            len(report.suggestions),
        )
        sent_any = True
    return sent_any


def _strip_for_inbox(html: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", html or "").strip()[:500]
