"""Evening decision report for currently held positions.

For each open position we produce a verdict — hold, take profit, sell, or swap
into one of tomorrow's recommendations — so the daily plan can tell the user what
to do with what they already own, like a broker's end-of-day review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Tomorrow's top pick must beat a holding's score by at least this to suggest a swap.
SWAP_SCORE_GAP = 2.0
# Lock-in suggestion once a holding is up this much (percent).
TAKE_PROFIT_WARN_PCT = 20.0
# "Near the protective floor" when within this percent above it.
NEAR_FLOOR_PCT = 3.0
# Legacy name kept for imports/tests — score gap (not PnL) drives swap suggestions.
# Take-profit / near-floor / max-days still win over swap when they apply.
STRONG_WINNER_PCT = 10.0

Verdict = str  # "hold" | "take_profit" | "sell" | "swap"


@dataclass
class HoldingReview:
    symbol: str
    verdict: Verdict
    pnl_pct: float
    days_held: int
    score: float
    reason: str
    capital_usd: float = 0.0
    swap_to: str | None = None
    swap_to_score: float | None = None
    last_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "verdict": self.verdict,
            "pnl_pct": round(self.pnl_pct, 2),
            "days_held": self.days_held,
            "score": round(self.score, 2),
            "reason": self.reason,
            "capital_usd": round(self.capital_usd, 2),
            "swap_to": self.swap_to,
            "swap_to_score": round(self.swap_to_score, 2) if self.swap_to_score is not None else None,
            "last_price": round(self.last_price, 2) if self.last_price is not None else None,
        }


def _best_replacement(
    symbol: str,
    my_score: float,
    recommendations: list[dict[str, Any]],
) -> tuple[str, float] | None:
    """Highest-scored tomorrow pick that clearly beats this holding."""
    best: tuple[str, float] | None = None
    for rec in recommendations:
        sym = str(rec.get("symbol"))
        if sym == symbol:
            continue
        score = float(rec.get("score", 0))
        if score - my_score < SWAP_SCORE_GAP:
            continue
        if best is None or score > best[1]:
            best = (sym, score)
    return best


def review_holding(
    holding: dict[str, Any],
    cfg: Any,
    scores: dict[str, dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> HoldingReview:
    symbol = str(holding["symbol"])
    capital_usd = float(holding.get("capital_usd", 0))
    entry = float(holding.get("entry_price") or 0)
    floor = float(holding.get("floor_price") or 0)
    days_held = int(holding.get("days_held", 0))
    max_days = int(getattr(cfg, "max_hold_days", 5))

    info = scores.get(symbol) or {}
    last = float(info.get("close") or 0)
    my_score = float(info.get("score") or 0)

    if last <= 0:
        for key in ("mark_price", "last_price"):
            alt = float(holding.get(key) or 0)
            if alt > 0:
                last = alt
                break

    if entry <= 0 or last <= 0:
        return HoldingReview(
            symbol=symbol,
            verdict="hold",
            pnl_pct=0.0,
            days_held=days_held,
            score=my_score,
            reason="אין נתוני מחיר עדכניים — המשך להחזיק",
            capital_usd=capital_usd,
            last_price=last or None,
        )

    pnl_pct = (last / entry - 1) * 100
    dist_floor_pct = (last / floor - 1) * 100 if floor > 0 else 100.0

    if dist_floor_pct <= NEAR_FLOOR_PCT:
        return HoldingReview(
            symbol, "sell", pnl_pct, days_held, my_score,
            reason=f"קרוב לרצפת ההגנה (${floor:.2f}) · שקול למכור",
            capital_usd=capital_usd,
            last_price=last,
        )

    if pnl_pct >= TAKE_PROFIT_WARN_PCT:
        return HoldingReview(
            symbol, "take_profit", pnl_pct, days_held, my_score,
            reason=f"רווח {pnl_pct:+.1f}% · שקול לממש חלק/הכל",
            capital_usd=capital_usd,
            last_price=last,
        )

    if days_held >= max_days - 1:
        return HoldingReview(
            symbol, "sell", pnl_pct, days_held, my_score,
            reason=f"מוחזק {days_held} ימים (מקס {max_days}) · ייסגר בקרוב",
            capital_usd=capital_usd,
            last_price=last,
        )

    # Score-first: if a new pick clearly beats this holding, suggest swap even
    # when the position is modestly green. Take-profit / floor / max-days above
    # already short-circuit before we get here.
    replacement = _best_replacement(symbol, my_score, recommendations)
    if replacement is not None:
        to_sym, to_score = replacement
        return HoldingReview(
            symbol, "swap", pnl_pct, days_held, my_score,
            reason=(
                f"יש מניה חזקה יותר בציונים ({to_sym} {to_score:.1f} "
                f"מול {my_score:.1f}) · שקול להחליף"
            ),
            capital_usd=capital_usd,
            swap_to=to_sym, swap_to_score=to_score, last_price=last,
        )

    return HoldingReview(
        symbol, "hold", pnl_pct, days_held, my_score,
        reason=f"מגמה תקינה ({pnl_pct:+.1f}%, ציון {my_score:.1f}) · המשך להחזיק",
        capital_usd=capital_usd,
        last_price=last,
    )


def backfill_holding_scores(
    holdings: list[dict[str, Any]],
    scores: dict[str, dict[str, Any]],
    *,
    as_of: Any | None = None,
) -> dict[str, dict[str, Any]]:
    """Ensure each open holding has a usable close in scores (evening plan PnL)."""
    from datetime import date as date_cls

    out = dict(scores)
    day = as_of if isinstance(as_of, date_cls) else date_cls.today()
    for h in holdings:
        sym = str(h.get("symbol") or "")
        if not sym:
            continue
        cur = out.get(sym) or {}
        if float(cur.get("close") or 0) > 0:
            continue
        close = 0.0
        try:
            from trading_pulse.agent.positions import fetch_day_ohlc

            bar = fetch_day_ohlc(sym, day)
            if bar:
                close = float(bar.get("close") or 0)
        except Exception:
            close = 0.0
        if close <= 0:
            try:
                from trading_pulse.agent.intraday_monitor import fetch_intraday_quote

                q = fetch_intraday_quote(sym)
                if q:
                    close = float(q.get("last") or 0)
            except Exception:
                close = 0.0
        if close <= 0:
            close = float(h.get("mark_price") or 0)
        if close > 0:
            merged = dict(cur)
            merged["close"] = close
            merged.setdefault("score", float(cur.get("score") or 0))
            out[sym] = merged
    return out


def review_holdings(
    holdings: list[dict[str, Any]],
    cfg: Any,
    scores: dict[str, dict[str, Any]],
    recommendations: list[dict[str, Any]] | None = None,
) -> list[HoldingReview]:
    recs = recommendations or []
    enriched = backfill_holding_scores(holdings, scores)
    reviews = [review_holding(h, cfg, enriched, recs) for h in holdings]
    return _dedupe_swap_targets(reviews)


def _dedupe_swap_targets(
    reviews: list[HoldingReview],
    *,
    max_swaps: int = 2,
) -> list[HoldingReview]:
    """Avoid spam like 4×«החלף → VLO» — keep the weakest holdings only."""
    swaps = [r for r in reviews if r.verdict == "swap" and r.swap_to]
    if len(swaps) <= max_swaps and len({r.swap_to for r in swaps}) == len(swaps):
        return reviews

    # Prefer unique targets; among same target keep lowest score / worst pnl first.
    swaps_sorted = sorted(
        swaps,
        key=lambda r: (r.score, r.pnl_pct, -(r.swap_to_score or 0)),
    )
    kept: list[HoldingReview] = []
    used_targets: set[str] = set()
    for rev in swaps_sorted:
        if len(kept) >= max_swaps:
            break
        target = str(rev.swap_to or "")
        if target in used_targets:
            continue
        used_targets.add(target)
        kept.append(rev)
    # If still under max and duplicates remain with unused capacity, allow one shared target.
    if len(kept) < max_swaps:
        for rev in swaps_sorted:
            if rev in kept:
                continue
            if len(kept) >= max_swaps:
                break
            kept.append(rev)

    keep_ids = {id(r) for r in kept}
    out: list[HoldingReview] = []
    for rev in reviews:
        if rev.verdict != "swap":
            out.append(rev)
            continue
        if id(rev) in keep_ids:
            out.append(rev)
        else:
            out.append(
                HoldingReview(
                    symbol=rev.symbol,
                    verdict="hold",
                    pnl_pct=rev.pnl_pct,
                    days_held=rev.days_held,
                    score=rev.score,
                    reason=(
                        f"מגמה תקינה ({rev.pnl_pct:+.1f}%, ציון {rev.score:.1f}) · "
                        "המשך להחזיק (החלפה מרוכזת בהצעות אחרות)"
                    ),
                    capital_usd=rev.capital_usd,
                    last_price=rev.last_price,
                )
            )
    return out


_VERDICT_CUBE = {
    "hold": ("החזק", "אין פעולה — ממשיכים להחזיק"),
    "sell": ("מכור", "שקול למכור למזומן"),
    "swap": ("החלף", "יש מניה חזקה יותר בציונים"),
    "take_profit": ("ממש רווח", "שקול לממש חלק או הכל"),
}


def build_portfolio_review_cubes(plan: dict[str, Any]) -> list[dict[str, str]]:
    """Labeled cubes for the pre-market holdings digest PNG."""
    from trading_pulse.agent.strategy_labels import strategy_label

    holdings = plan.get("holdings") or []
    actions = plan.get("holding_actions") or []
    by_sym = {str(a.get("symbol")): a for a in actions}
    cash = float(plan.get("available_capital_usd") or 0)
    held_syms = {str(h.get("symbol")) for h in holdings}
    new_n = sum(
        1
        for r in (plan.get("recommendations") or [])
        if not r.get("below_bar")
        and not r.get("approved")
        and not r.get("offer_skipped")
        and str(r.get("symbol")) not in held_syms
    )

    cubes: list[dict[str, str]] = [
        {
            "title": "מזומן פנוי",
            "blurb": "כמה אפשר לקנות בלי למכור מניה קיימת.",
            "value": f"${cash:.0f}" + (" · בלי מזומן — רק החלפה אם מומלץ" if cash < 1 else ""),
            "wide": "1",
        }
    ]

    for h in holdings:
        sym = str(h.get("symbol") or "")
        if not sym:
            continue
        a = by_sym.get(sym) or {}
        verdict = str(a.get("verdict") or "hold")
        label, default_blurb = _VERDICT_CUBE.get(verdict, ("החזק", "ממשיכים להחזיק"))
        pnl = float(a.get("pnl_pct") if a.get("pnl_pct") is not None else h.get("unrealized_pnl_pct") or 0)
        score = float(a.get("score") or 0)
        cap = float(a.get("capital_usd") or h.get("capital_usd") or 0)
        method = strategy_label(h) or strategy_label(a) or ""
        reason = str(a.get("reason") or default_blurb)
        value_bits = [f"${cap:.0f} מושקע", f"{pnl:+.1f}%", f"ציון {score:.1f}", label]
        if method:
            value_bits.insert(0, method)
        if verdict == "swap" and a.get("swap_to"):
            to_score = a.get("swap_to_score")
            to_bit = f"→ {a['swap_to']}"
            if to_score is not None:
                to_bit += f" (ציון {float(to_score):.1f})"
            value_bits.append(to_bit)
        cubes.append(
            {
                "title": sym,
                "blurb": reason,
                "value": " · ".join(value_bits),
                "wide": "1",
            }
        )

    if new_n:
        word = "הצעת קנייה אחת" if new_n == 1 else f"{new_n} הצעות קנייה"
        cubes.append(
            {
                "title": "המשך",
                "blurb": "הצעות חדשות נשלחות אחת-אחת אחרי הסקירה.",
                "value": f"יש {word} — בכל הצעה נבדוק גם החלפה מול התיק",
                "wide": "1",
            }
        )
    elif cash >= 20:
        cubes.append(
            {
                "title": "מזומן בלי הצעות חדשות",
                "blurb": "אפשר לחזק החזקה קיימת או להשאיר במזומן.",
                "value": f"תקנה SYMBOL ${min(int(cash), 100)} · או להשאיר",
                "wide": "1",
            }
        )
    return cubes


def swap_funding_for_offer(plan: dict[str, Any], offer_symbol: str) -> dict[str, Any] | None:
    """Best held name to sell/swap into this offer when scores clearly favor it."""
    offer_symbol = str(offer_symbol)
    offer_score = 0.0
    for rec in plan.get("recommendations") or []:
        if str(rec.get("symbol")) == offer_symbol:
            offer_score = float(rec.get("score") or rec.get("score_technical") or 0)
            break
    if offer_score <= 0:
        return None

    actions = list(plan.get("holding_actions") or [])
    preferred = [
        a
        for a in actions
        if str(a.get("verdict")) == "swap" and str(a.get("swap_to") or "") == offer_symbol
    ]
    pool = preferred or [
        a
        for a in actions
        if str(a.get("symbol") or "") != offer_symbol
        and str(a.get("verdict") or "hold") not in {"sell", "take_profit"}
        and offer_score - float(a.get("score") or 0) >= SWAP_SCORE_GAP
    ]
    if not pool:
        return None
    best = min(pool, key=lambda a: (float(a.get("score") or 0), float(a.get("pnl_pct") or 0)))
    from_sym = str(best.get("symbol") or "")
    if not from_sym:
        return None
    return {
        "from_symbol": from_sym,
        "to_symbol": offer_symbol,
        "from_score": float(best.get("score") or 0),
        "to_score": offer_score,
        "capital_usd": float(best.get("capital_usd") or 0),
        "pnl_pct": float(best.get("pnl_pct") or 0),
    }
