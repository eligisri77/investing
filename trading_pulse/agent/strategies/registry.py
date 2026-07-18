"""Single source of truth for strategy identity and user-selectable presets."""

from __future__ import annotations

from typing import Any

from trading_pulse.agent.strategies.models import StrategySpec

SCHEMA_VERSION = 2

STRATEGY_SPECS: dict[str, StrategySpec] = {
    "score_momentum": StrategySpec(
        id="score_momentum",
        label_he="מומנטום וציון",
        version="1.0",
        entry_policy="market_open",
        max_picks=3,
    ),
    "rising_three": StrategySpec(
        id="rising_three",
        label_he="נרות Rising Three",
        version="1.0",
        entry_policy="market_open",
        max_picks=1,
    ),
    "method2": StrategySpec(
        id="method2",
        label_he="שיטה 2 · נרות סיניים",
        version="1.0",
        entry_policy="stop_breakout",
        supported_sides=("LONG", "SHORT"),
        max_picks=1,
    ),
    "trend_pullback": StrategySpec(
        id="trend_pullback",
        label_he="תיקון בתוך מגמה",
        version="1.0",
        entry_policy="market_open",
        default_enabled=False,
        max_picks=1,
    ),
}

STRATEGY_MODES: dict[str, tuple[str, ...]] = {
    "balanced_mix": ("score_momentum", "rising_three", "method2"),
    "score_only": ("score_momentum",),
    "rising_three_only": ("rising_three",),
    "method2_only": ("method2",),
}


def enabled_strategy_ids(cfg: Any) -> tuple[str, ...]:
    mode = str(getattr(cfg, "strategy_mode", "balanced_mix") or "balanced_mix")
    enabled = list(STRATEGY_MODES.get(mode, STRATEGY_MODES["balanced_mix"]))
    if bool(getattr(cfg, "trend_pullback_enabled", False)):
        enabled.append("trend_pullback")
    return tuple(dict.fromkeys(enabled))


def strategy_metadata() -> list[dict[str, Any]]:
    return [spec.to_dict() for spec in STRATEGY_SPECS.values()]


def canonical_strategy_id(rec: dict[str, Any], *, score_profile: str = "momentum") -> str:
    raw = str(rec.get("strategy_id") or rec.get("strategy") or "score")
    if raw == "method2":
        return "method2"
    if raw in {"rising_three", "rising_three_methods"}:
        return "rising_three"
    if raw == "trend_pullback":
        return "trend_pullback"
    return "score_momentum"


def _confidence(strategy_id: str, native_score: float) -> float:
    # Native scales differ; normalization is explicit and intentionally simple.
    if strategy_id == "method2":
        return max(0.0, min(1.0, native_score / 10.0))
    if strategy_id == "rising_three":
        return max(0.0, min(1.0, native_score / 10.0))
    if strategy_id == "trend_pullback":
        return max(0.0, min(1.0, native_score / 10.0))
    return max(0.0, min(1.0, native_score / 12.0))


def annotate_recommendation(
    rec: dict[str, Any],
    *,
    score_profile: str = "momentum",
) -> dict[str, Any]:
    """Add backward-compatible strategy attribution to an existing recommendation."""
    strategy_id = canonical_strategy_id(rec, score_profile=score_profile)
    spec = STRATEGY_SPECS[strategy_id]
    native_score = float(rec.get("native_score", rec.get("score", 0)) or 0)
    contributors = list(rec.get("contributing_strategies") or [strategy_id])
    rec.update(
        {
            "schema_version": SCHEMA_VERSION,
            "strategy_id": strategy_id,
            "strategy_version": spec.version,
            "native_score": round(native_score, 4),
            "confidence": round(
                max(float(rec.get("confidence") or 0), _confidence(strategy_id, native_score)),
                4,
            ),
            "entry_policy": rec.get("entry_policy") or spec.entry_policy,
            "contributing_strategies": list(dict.fromkeys(contributors)),
        }
    )
    return rec
