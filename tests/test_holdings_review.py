"""Tests for the evening holdings decision report."""

from __future__ import annotations

from dataclasses import dataclass

from trading_pulse.agent.holdings_review import (
    SWAP_SCORE_GAP,
    build_portfolio_review_cubes,
    held_funding_candidates,
    review_holding,
    review_holdings,
    swap_funding_for_offer,
)


@dataclass
class FakeCfg:
    max_hold_days: int = 5
    stop_loss_pct: float = 0.12
    take_profit_pct: float = 0.25


def _holding(symbol, entry, floor, days=1):
    return {"symbol": symbol, "entry_price": entry, "floor_price": floor, "days_held": days}


def test_hold_when_healthy():
    cfg = FakeCfg()
    h = _holding("HOOD", 100.0, 88.0, days=1)
    scores = {"HOOD": {"score": 7.5, "close": 105.0}}
    r = review_holding(h, cfg, scores, [])
    assert r.verdict == "hold"
    assert round(r.pnl_pct) == 5


def test_sell_when_near_floor():
    cfg = FakeCfg()
    h = _holding("SOXL", 197.0, 159.0, days=1)
    scores = {"SOXL": {"score": 4.0, "close": 162.0}}  # ~1.9% above floor
    r = review_holding(h, cfg, scores, [])
    assert r.verdict == "sell"


def test_take_profit_when_up_big():
    cfg = FakeCfg()
    h = _holding("MSTR", 100.0, 88.0, days=2)
    scores = {"MSTR": {"score": 8.0, "close": 125.0}}  # +25%
    r = review_holding(h, cfg, scores, [])
    assert r.verdict == "take_profit"


def test_sell_when_max_hold_days_reached():
    cfg = FakeCfg(max_hold_days=5)
    h = _holding("AMD", 100.0, 88.0, days=4)
    scores = {"AMD": {"score": 7.0, "close": 103.0}}
    r = review_holding(h, cfg, scores, [])
    assert r.verdict == "sell"


def test_swap_when_better_pick_tomorrow():
    cfg = FakeCfg()
    h = _holding("AMD", 100.0, 88.0, days=1)
    scores = {"AMD": {"score": 6.0, "close": 102.0}}
    recs = [{"symbol": "NVDA", "score": 9.0}]
    r = review_holding(h, cfg, scores, recs)
    assert r.verdict == "swap"
    assert r.swap_to == "NVDA"


def test_swap_when_better_score_even_if_modest_winner():
    """Score gap drives swap — modest green PnL no longer blocks rotation."""
    cfg = FakeCfg()
    h = _holding("AMD", 100.0, 88.0, days=1)
    scores = {"AMD": {"score": 6.0, "close": 115.0}}  # +15%
    recs = [{"symbol": "NVDA", "score": 9.0}]
    r = review_holding(h, cfg, scores, recs)
    assert r.verdict == "swap"
    assert r.swap_to == "NVDA"


def test_take_profit_beats_swap_when_up_big():
    cfg = FakeCfg()
    h = _holding("AMD", 100.0, 88.0, days=1)
    scores = {"AMD": {"score": 6.0, "close": 125.0}}  # +25%
    recs = [{"symbol": "NVDA", "score": 9.0}]
    r = review_holding(h, cfg, scores, recs)
    assert r.verdict == "take_profit"


def test_hold_when_no_price_data():
    cfg = FakeCfg()
    h = _holding("XYZ", 50.0, 44.0, days=1)
    r = review_holding(h, cfg, {}, [])
    assert r.verdict == "hold"
    assert "אין נתוני מחיר" in r.reason


def test_mark_price_fallback_when_score_close_missing():
    cfg = FakeCfg()
    h = _holding("META", 100.0, 88.0, days=1)
    h["mark_price"] = 103.0
    r = review_holding(h, cfg, {}, [])
    assert r.verdict == "hold"
    assert round(r.pnl_pct) == 3
    assert "אין נתוני מחיר" not in r.reason


def test_review_holdings_batch_and_serialize():
    cfg = FakeCfg()
    holdings = [_holding("HOOD", 100.0, 88.0), _holding("SOXL", 197.0, 159.0)]
    scores = {"HOOD": {"score": 7.5, "close": 105.0}, "SOXL": {"score": 4.0, "close": 161.0}}
    reviews = review_holdings(holdings, cfg, scores, [])
    assert len(reviews) == 2
    d = reviews[0].to_dict()
    assert set(d) >= {"symbol", "verdict", "pnl_pct", "reason"}


def test_dedupe_swap_targets_caps_at_two_and_prefers_unique():
    from trading_pulse.agent.holdings_review import HoldingReview, _dedupe_swap_targets

    reviews = [
        HoldingReview(
            "A", "swap", -5.0, 1, 3.0, "swap", swap_to="VLO", swap_to_score=10.0
        ),
        HoldingReview(
            "B", "swap", -4.0, 1, 4.0, "swap", swap_to="VLO", swap_to_score=10.0
        ),
        HoldingReview(
            "C", "swap", -3.0, 1, 5.0, "swap", swap_to="VLO", swap_to_score=10.0
        ),
        HoldingReview(
            "D", "swap", -2.0, 1, 6.0, "swap", swap_to="NVDA", swap_to_score=12.0
        ),
        HoldingReview("E", "hold", 1.0, 1, 7.0, "ok"),
    ]
    out = _dedupe_swap_targets(reviews, max_swaps=2)
    swaps = [r for r in out if r.verdict == "swap"]
    assert len(swaps) == 2
    assert {r.swap_to for r in swaps} == {"VLO", "NVDA"}
    assert {r.symbol for r in swaps} == {"A", "D"}
    demoted = {r.symbol for r in out if r.verdict == "hold"}
    assert {"B", "C", "E"} <= demoted
    assert any("החלפה מרוכזת" in r.reason for r in out if r.symbol in {"B", "C"})


def test_dedupe_swap_targets_noop_when_already_few_unique():
    from trading_pulse.agent.holdings_review import HoldingReview, _dedupe_swap_targets

    reviews = [
        HoldingReview(
            "A", "swap", -1.0, 1, 5.0, "swap", swap_to="NVDA", swap_to_score=12.0
        ),
        HoldingReview(
            "B", "swap", -2.0, 1, 4.0, "swap", swap_to="TSLA", swap_to_score=11.0
        ),
        HoldingReview("C", "hold", 2.0, 1, 8.0, "ok"),
    ]
    out = _dedupe_swap_targets(reviews, max_swaps=2)
    assert [r.verdict for r in out] == ["swap", "swap", "hold"]
    assert [r.swap_to for r in out if r.verdict == "swap"] == ["NVDA", "TSLA"]


def test_review_holdings_dedupes_many_swaps_to_same_target():
    """Four weak holdings all pointing at one pick → at most two swap lines."""
    cfg = FakeCfg()
    holdings = [
        _holding("W1", 100.0, 88.0),
        _holding("W2", 100.0, 88.0),
        _holding("W3", 100.0, 88.0),
        _holding("W4", 100.0, 88.0),
    ]
    scores = {
        "W1": {"score": 3.0, "close": 99.0},
        "W2": {"score": 4.0, "close": 98.0},
        "W3": {"score": 5.0, "close": 97.0},
        "W4": {"score": 6.0, "close": 96.0},
    }
    recs = [{"symbol": "VLO", "score": 12.0}]
    reviews = review_holdings(holdings, cfg, scores, recs)
    swaps = [r for r in reviews if r.verdict == "swap"]
    assert len(swaps) <= 2
    assert all(r.swap_to == "VLO" for r in swaps)


# --------------------------------------------------------------------------
# held_funding_candidates / swap_funding_for_offer / build_portfolio_review_cubes
# --------------------------------------------------------------------------


def test_held_funding_candidates_orders_weakest_first_and_excludes_offer():
    plan = {
        "holdings": [
            {"symbol": "META", "capital_usd": 300, "score": 9.0, "unrealized_pnl_pct": 5.0},
            {"symbol": "AMZN", "capital_usd": 200, "score": 4.0, "unrealized_pnl_pct": -2.0},
            {"symbol": "NVDA", "capital_usd": 150, "score": 14.0},  # offer itself
            {"symbol": "CDNA", "capital_usd": 100, "score": 4.0, "unrealized_pnl_pct": 1.0},
        ],
        "holding_actions": [
            {"symbol": "AMZN", "score": 4.0, "pnl_pct": -2.0, "capital_usd": 200},
            {"symbol": "CDNA", "score": 4.0, "pnl_pct": 1.0, "capital_usd": 100},
            {"symbol": "META", "score": 9.0, "pnl_pct": 5.0, "capital_usd": 300},
        ],
    }
    rows = held_funding_candidates(plan, "NVDA", limit=3)
    assert [r["symbol"] for r in rows] == ["AMZN", "CDNA", "META"]
    assert "NVDA" not in {r["symbol"] for r in rows}
    assert rows[0]["capital_usd"] == 200.0
    assert rows[0]["pnl_pct"] == -2.0


def test_held_funding_candidates_includes_actions_only_and_respects_limit():
    plan = {
        "holdings": [{"symbol": "U", "capital_usd": 50}],
        "holding_actions": [
            {"symbol": "PATH", "score": 3.0, "pnl_pct": -8.0, "capital_usd": 180},
            {"symbol": "U", "score": 7.0, "pnl_pct": 2.0, "capital_usd": 50},
            {"symbol": "BEAM", "score": 5.0, "pnl_pct": 0.0, "capital_usd": 90},
        ],
    }
    rows = held_funding_candidates(plan, "NVDA", limit=2)
    assert [r["symbol"] for r in rows] == ["PATH", "BEAM"]
    assert held_funding_candidates({"holdings": [], "holding_actions": []}, "NVDA") == []


def test_approved_pending_funding_when_book_empty_after_premarket_swap():
    from trading_pulse.agent.holdings_review import (
        approved_pending_funding_candidates,
        funding_candidates_for_offer,
        suggested_reallocate_amount,
    )

    plan = {
        "holdings": [],  # TSLL sold; ELF not filled yet
        "holding_actions": [],
        "recommendations": [
            {
                "symbol": "ELF",
                "approved": True,
                "capital_usd": 950.0,
                "score": 10.4,
            },
            {"symbol": "U", "approved": False, "score": 10.2, "capital_usd": 0},
        ],
    }
    pending = approved_pending_funding_candidates(plan, "U", limit=3)
    assert [r["symbol"] for r in pending] == ["ELF"]
    assert pending[0]["source"] == "approved_pending"
    assert funding_candidates_for_offer(plan, "U")[0]["symbol"] == "ELF"

    po = {"queue": ["U", "A", "B", "C"], "index": 0, "decided": {"ELF": 950}}
    # 1 donor share + 4 remaining offers → $190 each
    amt, donor = suggested_reallocate_amount(plan, po, "U")
    assert donor == "ELF"
    assert amt == 190.0


def test_funding_candidates_prefers_held_over_approved_pending():
    """Open book funding wins even when another name is approved-pending."""
    from trading_pulse.agent.holdings_review import (
        approved_pending_funding_candidates,
        funding_candidates_for_offer,
    )

    plan = {
        "holdings": [
            {"symbol": "AMZN", "capital_usd": 200, "score": 4.0, "unrealized_pnl_pct": -1.0},
        ],
        "holding_actions": [
            {"symbol": "AMZN", "score": 4.0, "pnl_pct": -1.0, "capital_usd": 200},
        ],
        "recommendations": [
            {"symbol": "ELF", "approved": True, "capital_usd": 950.0, "score": 10.4},
            {"symbol": "U", "approved": False, "score": 10.2, "capital_usd": 0},
        ],
    }
    rows = funding_candidates_for_offer(plan, "U", limit=3)
    assert [r["symbol"] for r in rows] == ["AMZN"]
    assert rows[0]["source"] == "held"
    # Pending still exists as a fallback source — just not preferred while held names remain.
    assert [r["symbol"] for r in approved_pending_funding_candidates(plan, "U")] == ["ELF"]


def test_approved_pending_excludes_held_and_terminal_method2():
    from trading_pulse.agent.holdings_review import approved_pending_funding_candidates

    plan = {
        "holdings": [{"symbol": "PATH", "capital_usd": 100}],
        "recommendations": [
            {"symbol": "PATH", "approved": True, "capital_usd": 100.0},  # already held
            {
                "symbol": "BEAM",
                "approved": True,
                "capital_usd": 200.0,
                "method2_status": "filled",
            },
            {
                "symbol": "SOXL",
                "approved": True,
                "capital_usd": 0.5,  # below $1
            },
            {"symbol": "ELF", "approved": True, "capital_usd": 400.0, "score": 9.0},
            {"symbol": "U", "approved": False, "capital_usd": 50.0},
        ],
    }
    rows = approved_pending_funding_candidates(plan, "NVDA", limit=5)
    assert [r["symbol"] for r in rows] == ["ELF"]
    assert rows[0]["source"] == "approved_pending"


def test_swap_funding_prefers_explicit_swap_to():
    plan = {
        "recommendations": [{"symbol": "NVDA", "score": 12.0}],
        "holding_actions": [
            {
                "symbol": "AMD",
                "verdict": "swap",
                "swap_to": "NVDA",
                "score": 6.0,
                "pnl_pct": 2.0,
                "capital_usd": 200,
            },
            {
                "symbol": "META",
                "verdict": "hold",
                "score": 4.0,  # weaker — would win score-gap fallback
                "pnl_pct": -1.0,
                "capital_usd": 250,
            },
        ],
    }
    out = swap_funding_for_offer(plan, "NVDA")
    assert out is not None
    assert out["from_symbol"] == "AMD"
    assert out["to_symbol"] == "NVDA"
    assert out["from_score"] == 6.0
    assert out["to_score"] == 12.0
    assert out["capital_usd"] == 200.0


def test_swap_funding_score_gap_fallback_picks_weakest_hold():
    """No explicit swap_to → fund from lowest-score hold that loses by ≥ SWAP_SCORE_GAP."""
    plan = {
        "recommendations": [{"symbol": "NVDA", "score": 10.0}],
        "holding_actions": [
            {"symbol": "META", "verdict": "hold", "score": 8.5, "pnl_pct": 1.0, "capital_usd": 300},
            {"symbol": "AMD", "verdict": "hold", "score": 6.0, "pnl_pct": 3.0, "capital_usd": 200},
            {"symbol": "SOXL", "verdict": "sell", "score": 3.0, "pnl_pct": -5.0, "capital_usd": 150},
        ],
    }
    assert 10.0 - 6.0 >= SWAP_SCORE_GAP
    assert 10.0 - 8.5 < SWAP_SCORE_GAP
    out = swap_funding_for_offer(plan, "NVDA")
    assert out is not None
    assert out["from_symbol"] == "AMD"
    assert out["from_score"] == 6.0
    # sell / take_profit excluded from fallback pool
    assert out["from_symbol"] != "SOXL"


def test_swap_funding_none_when_gap_too_small_or_offer_score_missing():
    plan = {
        "recommendations": [{"symbol": "NVDA", "score": 8.0}],
        "holding_actions": [
            {"symbol": "AMD", "verdict": "hold", "score": 7.0, "pnl_pct": 1.0},
        ],
    }
    assert swap_funding_for_offer(plan, "NVDA") is None
    assert swap_funding_for_offer({"recommendations": [], "holding_actions": []}, "NVDA") is None


def test_build_portfolio_review_cubes_cash_and_per_holding():
    plan = {
        "available_capital_usd": 0,
        "holdings": [
            {"symbol": "AMD", "capital_usd": 200, "strategy_id": "score_momentum"},
            {"symbol": "META", "capital_usd": 250},
        ],
        "holding_actions": [
            {
                "symbol": "AMD",
                "verdict": "swap",
                "pnl_pct": 5.0,
                "score": 6.0,
                "capital_usd": 200,
                "swap_to": "NVDA",
                "swap_to_score": 12.0,
                "reason": "יש מניה חזקה יותר",
            },
            {
                "symbol": "META",
                "verdict": "hold",
                "pnl_pct": 2.0,
                "score": 9.0,
                "capital_usd": 250,
                "reason": "מגמה תקינה",
            },
        ],
        "recommendations": [{"symbol": "NVDA", "score": 12.0}],
    }
    cubes = build_portfolio_review_cubes(plan)
    titles = [c["title"] for c in cubes]
    assert titles[0] == "מניות בתיק"
    assert "AMD" in cubes[0]["value"] and "META" in cubes[0]["value"]
    assert titles[1] == "מזומן פנוי"
    assert "$0" in cubes[1]["value"]
    assert "בלי מזומן" in cubes[1]["value"]
    assert "AMD" in titles
    assert "META" in titles
    amd = next(c for c in cubes if c["title"] == "AMD")
    assert "החלף" in amd["value"]
    assert "→ NVDA" in amd["value"]
    assert "ציון 12.0" in amd["value"]
    assert cubes[-1]["title"] == "המשך"
    assert "הצעת קנייה" in cubes[-1]["value"]


def test_build_portfolio_review_cubes_empty_holdings_inventory():
    """Empty book still leads with «מניות בתיק» saying there are none."""
    plan = {
        "available_capital_usd": 500,
        "holdings": [],
        "holding_actions": [],
        "recommendations": [{"symbol": "NVDA", "score": 12.0}],
    }
    cubes = build_portfolio_review_cubes(plan)
    assert cubes[0]["title"] == "מניות בתיק"
    assert cubes[0]["value"] == "אין מניות בתיק"
    assert cubes[1]["title"] == "מזומן פנוי"
    assert "$500" in cubes[1]["value"]


def test_build_portfolio_review_cubes_cash_topup_when_no_new_offers():
    plan = {
        "available_capital_usd": 80,
        "holdings": [{"symbol": "META", "capital_usd": 250}],
        "holding_actions": [
            {"symbol": "META", "verdict": "hold", "pnl_pct": 1.0, "score": 8.0, "capital_usd": 250},
        ],
        "recommendations": [],
    }
    cubes = build_portfolio_review_cubes(plan)
    assert cubes[0]["title"] == "מניות בתיק"
    assert "META" in cubes[0]["value"]
    assert cubes[1]["title"] == "מזומן פנוי"
    assert "$80" in cubes[1]["value"]
    assert "בלי מזומן" not in cubes[1]["value"]
    assert any(c["title"] == "מזומן בלי הצעות חדשות" for c in cubes)
    tip = next(c for c in cubes if c["title"] == "מזומן בלי הצעות חדשות")
    assert "תקנה META" in tip["value"]
    assert "תקנה SYMBOL" not in tip["value"]
    assert "$80" in tip["value"]
