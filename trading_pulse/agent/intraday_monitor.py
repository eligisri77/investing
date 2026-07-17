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
        pnl_txt = f"{pnl_pct:+.1f}% מהכניסה · " if entry > 0 and last > 0 else ""
        if kinds & {"near_stop", "floor_breach"}:
            lead = "קרוב לרף"
        elif "heavy_loss" in kinds or (
            "intraday_drop" in kinds and day_pct <= SELL_STRONG_DROP_PCT
        ):
            lead = "ירידה חדה"
        else:
            lead = "אזהרת מכירה"

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
                        f"{lead} · {pnl_txt}מוכר ${sold_usd:.0f} מ-{sym} → קונה {to_sym} "
                        f"(ציון {float(to_data.get('score', 0)):.1f})"
                    ),
                )
            )
        else:
            out.append(
                TradeSuggestion(
                    kind="sell",
                    symbol=sym,
                    message=(
                        f"{lead} · {pnl_txt}אין מועמדת חזקה — "
                        f"מכירה למזומן עד הזדמנות"
                    ),
                )
            )
    return out


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

    suggestions: list[TradeSuggestion] = _sell_recommendations(
        cfg, holdings, quotes, alerts_by_symbol, scores, skip
    )
    sell_symbols: set[str] = set()
    for s in suggestions:
        if s.kind == "sell":
            sell_symbols.add(s.symbol)
        elif s.kind == "swap" and s.swap_from:
            sell_symbols.add(str(s.swap_from))

    if not scores:
        return suggestions

    top = _top_candidate(cfg, scores, skip)
    if top is None:
        return suggestions
    best_sym, best = top

    max_open = int(getattr(cfg, "max_open_positions", 4))
    open_slots = max(0, max_open - len(holdings))

    if open_slots > 0:
        from trading_pulse.agent.positions import available_capital

        state_obj = state or {"equity": 0, "open_positions": holdings}
        cash = available_capital(cfg, state_obj)
        equity = float(state_obj.get("equity", 0)) or cash + sum(
            float(p.get("capital_usd", 0)) for p in holdings
        )
        pos_pct = float(getattr(cfg, "max_position_pct", 0.34))
        buy_usd = round(min(max(cash, 0), equity * pos_pct), 0) if cash > 0 else round(equity * pos_pct, 0)
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
    now: datetime | None = None,
) -> IntradayReport:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cooldowns: dict[str, str] = state.setdefault("intraday_alert_cooldowns", {})
    cutoff = now - timedelta(minutes=cooldown_minutes)

    def fresh(key: str) -> bool:
        ts = cooldowns.get(key)
        if not ts:
            return True
        try:
            prev = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            return prev < cutoff
        except ValueError:
            return True

    report.alerts = [
        a for a in report.alerts if fresh(_cooldown_key(a.symbol, a.kind))
    ]
    report.suggestions = [
        s
        for s in report.suggestions
        if fresh(_cooldown_key(s.symbol, f"suggest_{s.kind}"))
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
        send_user_notification,
    )
    from trading_pulse.core.app_paths import STATE_FILE
    from trading_pulse.core.schedule_tz import us_trading_session_date
    from trading_pulse.telegram.telegram_format import (
        format_entry_notification,
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
                msg = format_entry_notification(
                    m2_fills,
                    trading_day=today.isoformat(),
                    subtitle="שיטה 2 · פריצה תוך־יומית",
                )
                if msg and send_user_notification(
                    cfg, msg, context="entry:method2", parse_mode="HTML"
                ):
                    sent_any = True
                logging.info("Method2 intraday: filled %d", len(m2_fills))
    except Exception as ex:
        logging.warning("Method2 intraday fill failed: %s", ex)

    report = build_intraday_report(cfg, state)
    cooldown = int(getattr(cfg, "intraday_alert_cooldown_minutes", DEFAULT_COOLDOWN_MINUTES))
    report = filter_cooled_down(report, state, cooldown)

    if not report.has_content:
        if not sent_any:
            logging.info("Intraday check: nothing noteworthy")
        return sent_any

    text = format_intraday_monitor(report)
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
