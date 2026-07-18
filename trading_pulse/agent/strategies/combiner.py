"""Deterministic portfolio-level combination of heterogeneous strategy signals."""

from __future__ import annotations

from typing import Any

from trading_pulse.agent.strategies.registry import annotate_recommendation

_PRIORITY = {
    "method2": 4,
    "vcp_breakout": 3,
    "rising_three": 3,
    "relative_strength": 2,
    "trend_pullback": 2,
    "score_momentum": 1,
}


def combine_recommendations(
    recommendations: list[dict[str, Any]],
    *,
    max_picks: int,
    score_profile: str = "momentum",
) -> list[dict[str, Any]]:
    """Merge duplicate symbols, reward confluence, and enforce a portfolio cap."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for raw in recommendations:
        rec = annotate_recommendation(dict(raw), score_profile=score_profile)
        symbol = str(rec.get("symbol") or "").upper()
        if not symbol:
            continue
        if symbol not in grouped:
            grouped[symbol] = []
            order.append(symbol)
        grouped[symbol].append(rec)

    merged: list[dict[str, Any]] = []
    for symbol in order:
        rows = grouped[symbol]
        rows.sort(
            key=lambda r: (
                _PRIORITY.get(str(r.get("strategy_id")), 0),
                float(r.get("confidence") or 0),
            ),
            reverse=True,
        )
        primary = dict(rows[0])
        contributors = list(
            dict.fromkeys(
                str(r.get("strategy_id"))
                for r in rows
                if r.get("strategy_id")
            )
        )
        primary["contributing_strategies"] = contributors
        primary["confluence_count"] = len(contributors)
        primary["confidence"] = round(
            min(
                1.0,
                max(float(r.get("confidence") or 0) for r in rows)
                + 0.08 * max(0, len(contributors) - 1),
            ),
            4,
        )
        if len(contributors) > 1:
            primary["reason"] = (
                f"{primary.get('reason', '')} · הסכמה בין "
                f"{len(contributors)} אסטרטגיות"
            ).strip(" ·")
        merged.append(primary)

    merged.sort(
        key=lambda r: (
            int(r.get("confluence_count") or 1),
            float(r.get("confidence") or 0),
            float(r.get("score") or 0),
        ),
        reverse=True,
    )
    return merged[: max(0, int(max_picks))]


def allocate_combined_capital(
    recommendations: list[dict[str, Any]],
    *,
    deployable: float,
) -> None:
    """Preserve stop-risk sleeve sizing; split remaining cash across other picks."""
    sleeves = [
        r
        for r in recommendations
        if str(r.get("strategy_id") or "") == "method2" or r.get("sleeve")
    ]
    mains = [r for r in recommendations if r not in sleeves]
    available = max(0.0, float(deployable))
    requested = [
        max(0.0, float(rec.get("capital_usd") or 0)) for rec in sleeves
    ]
    requested_total = sum(requested)
    if requested_total > available and requested_total > 0:
        scale = available / requested_total
        allocated = [round(amount * scale, 2) for amount in requested]
        if allocated:
            allocated[-1] = round(
                allocated[-1] + available - sum(allocated),
                2,
            )
        for rec, amount in zip(sleeves, allocated):
            rec["capital_usd"] = amount
    sleeve_total = min(available, requested_total)
    main_budget = max(0.0, float(deployable) - sleeve_total)
    each = main_budget / len(mains) if mains else 0.0
    for rec in mains:
        rec["capital_usd"] = round(each, 2)
