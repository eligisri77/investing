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
# Don't rotate out of a clear winner even if a higher-scored pick exists.
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

    if pnl_pct < STRONG_WINNER_PCT:
        replacement = _best_replacement(symbol, my_score, recommendations)
        if replacement is not None:
            to_sym, to_score = replacement
            return HoldingReview(
                symbol, "swap", pnl_pct, days_held, my_score,
                reason=f"מחר יש מניה חזקה יותר ({to_sym} ציון {to_score:.1f} מול {my_score:.1f})",
                capital_usd=capital_usd,
                swap_to=to_sym, swap_to_score=to_score, last_price=last,
            )

    return HoldingReview(
        symbol, "hold", pnl_pct, days_held, my_score,
        reason=f"מגמה תקינה ({pnl_pct:+.1f}%, ציון {my_score:.1f}) · המשך להחזיק",
        capital_usd=capital_usd,
        last_price=last,
    )


def review_holdings(
    holdings: list[dict[str, Any]],
    cfg: Any,
    scores: dict[str, dict[str, Any]],
    recommendations: list[dict[str, Any]] | None = None,
) -> list[HoldingReview]:
    recs = recommendations or []
    return [review_holding(h, cfg, scores, recs) for h in holdings]
