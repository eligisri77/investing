"""Typed strategy boundary used by plan generation and reporting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Side = Literal["LONG", "SHORT"]
EntryPolicy = Literal["market_open", "stop_breakout"]


@dataclass(frozen=True)
class StrategySpec:
    id: str
    label_he: str
    version: str
    entry_policy: EntryPolicy
    supported_sides: tuple[Side, ...] = ("LONG",)
    default_enabled: bool = True
    max_picks: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StrategySignal:
    strategy_id: str
    strategy_version: str
    symbol: str
    side: Side
    native_score: float
    confidence: float
    reason: str
    entry_policy: EntryPolicy
    entry_ref_price: float
    stop_loss_price: float
    take_profit_price: float
    requested_capital_usd: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)
    contributing_strategies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["confidence"] = round(max(0.0, min(1.0, self.confidence)), 4)
        return data
