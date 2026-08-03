"""Tests for the sequential one-at-a-time buy-offer state machine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trading_pulse.agent import offer_queue
from trading_pulse.agent.offer_queue import (
    build_offer_action_cubes,
    build_offer_metric_cubes,
    cash_remaining,
    current_offer_symbol,
    eligible_offer_symbols,
    expire_stale_offer,
    finish_offers,
    format_offer_prompt,
    maybe_nudge_offer,
    pending_offer,
    start_and_send_first_offer,
    start_offer_queue,
    suggested_amount,
    try_resolve_pending_offer,
)


def _plan(**overrides) -> dict:
    plan = {
        "for_trading_day": "2026-07-20",
        "available_capital_usd": 300.0,
        "holdings": [],
        "recommendations": [
            {"symbol": "NVDA", "score": 14.0, "explanation": "מומנטום חזק"},
            {"symbol": "AMD", "score": 10.0, "explanation": "נפח גבוה"},
        ],
    }
    plan.update(overrides)
    return plan


# --------------------------------------------------------------------------
# eligible_offer_symbols
# --------------------------------------------------------------------------


def test_eligible_offer_symbols_excludes_held_below_bar_and_decided():
    plan = _plan(
        holdings=[{"symbol": "AMD"}],
        recommendations=[
            {"symbol": "NVDA"},
            {"symbol": "AMD"},  # already held
            {"symbol": "TSLA", "below_bar": True},
            {"symbol": "META", "approved": True},
            {"symbol": "RIVN", "offer_skipped": True},
            {"symbol": "PYPL"},
        ],
    )
    assert eligible_offer_symbols(plan) == ["NVDA", "PYPL"]


def test_eligible_offer_symbols_empty_when_no_recs():
    assert eligible_offer_symbols(_plan(recommendations=[])) == []


# --------------------------------------------------------------------------
# start_offer_queue / pending_offer / current_offer_symbol
# --------------------------------------------------------------------------


def test_start_offer_queue_seeds_state():
    state: dict = {}
    plan = _plan()
    assert start_offer_queue(state, plan) is True
    po = state["pending_offer"]
    assert po["trading_day"] == "2026-07-20"
    assert po["queue"] == ["NVDA", "AMD"]
    assert po["index"] == 0
    assert po["decided"] == {}
    assert po["offered_at"] is None
    assert po["nudged_at"] is None


def test_start_offer_queue_false_and_clears_stale_when_empty():
    state = {"pending_offer": {"queue": ["OLD"], "index": 0}}
    plan = _plan(recommendations=[])
    assert start_offer_queue(state, plan) is False
    assert "pending_offer" not in state


def test_pending_offer_none_variants():
    assert pending_offer({}) is None
    assert pending_offer({"pending_offer": {"queue": []}}) is None
    assert (
        pending_offer({"pending_offer": {"queue": ["A"], "index": 1}}) is None
    )  # index past end
    po = pending_offer({"pending_offer": {"queue": ["A"], "index": 0}})
    assert po is not None


def test_current_offer_symbol():
    state = {"pending_offer": {"queue": ["NVDA", "AMD"], "index": 1}}
    assert current_offer_symbol(state) == "AMD"
    assert current_offer_symbol({}) is None


# --------------------------------------------------------------------------
# suggested_amount / cash_remaining
# --------------------------------------------------------------------------


def test_suggested_amount_equal_split_of_remaining_cash():
    plan = _plan(available_capital_usd=300.0)
    po = {"queue": ["NVDA", "AMD", "PYPL"], "index": 0, "decided": {}}
    assert suggested_amount(plan, po) == 100.0
    po["decided"] = {"NVDA": 120.0}
    po["index"] = 1
    # Remaining cash 180 split across 2 un-decided offers
    assert suggested_amount(plan, po) == 90.0


def test_suggested_amount_never_divides_by_zero():
    plan = _plan(available_capital_usd=100.0)
    po = {"queue": ["NVDA"], "index": 5, "decided": {}}  # index past queue len
    assert suggested_amount(plan, po) == 100.0


def test_cash_remaining_subtracts_decided_amounts():
    plan = _plan(available_capital_usd=300.0)
    po = {"decided": {"NVDA": 100.0, "AMD": 50.0}}
    assert cash_remaining(plan, po) == 150.0


def test_cash_remaining_never_negative():
    plan = _plan(available_capital_usd=100.0)
    po = {"decided": {"NVDA": 150.0}}
    assert cash_remaining(plan, po) == 0.0


def test_build_offer_metric_cubes_speculative_has_labeled_blocks():
    rec = {
        "symbol": "RBLX",
        "score": 13.0,
        "atr_pct": 5.7,
        "breakout_ok": False,
        "near_high_pct": -14.7,
        "ret_5d_pct": 2.4,
        "vol_ratio": 3.33,
        "volume_ok": True,
        "strategy": "score",
        "strategy_id": "score_momentum",
        "entry_policy": "market_open",
        "source_scores": {"finviz": 14.1, "nasdaq": 13.2, "yahoo": 13.0},
        "sources_used": 3,
        "backtest": {"summary": "90d · win 62% · 13 trades"},
    }
    cubes = build_offer_metric_cubes(rec, rank=1)
    titles = [c["title"] for c in cubes]
    assert "שיטת כניסה" in titles
    assert "ציון ותנודתיות" in titles
    assert "מומנטום ומחיר" in titles
    assert "נפח" in titles
    assert "חדשות ומקורות" in titles
    assert "בדיקה לאחור" in titles
    assert all(c.get("blurb") for c in cubes)
    method_cube = next(c for c in cubes if c["title"] == "שיטת כניסה")
    assert "מומנטום" in method_cube["value"]
    assert "בפתיחה" in method_cube["value"]


def test_build_offer_metric_cubes_method2_variant():
    rec = {
        "symbol": "PATH",
        "strategy": "method2",
        "strategy_id": "method2",
        "entry_policy": "stop_breakout",
        "side": "LONG",
        "trigger": "3-2-2",
        "method2_entry_ref": 12.5,
        "method2_stop_ref": 11.0,
        "score": 9.0,
        "vol_ratio": 1.2,
        "volume_ok": True,
    }
    cubes = build_offer_metric_cubes(rec, rank=2)
    by_title = {c["title"]: c for c in cubes}
    assert "שיטת כניסה" in by_title
    assert "נרות סיניים 2" in by_title["שיטת כניסה"]["value"]
    assert "בפריצה" in by_title["שיטת כניסה"]["value"]
    assert "נרות סיניים 2" in by_title
    assert "ציון ותנודתיות" not in by_title
    assert "מומנטום ומחיר" not in by_title
    m2 = by_title["נרות סיניים 2"]
    assert "רמות הפריצה" in m2["blurb"]
    assert "לונג" in m2["value"]
    assert "3-2-2" in m2["value"]
    assert "$12.50" in m2["value"]
    assert "$11.00" in m2["value"]
    assert m2.get("wide") == "1"
    assert "נפח" in by_title
    assert "בדיקה לאחור" in by_title


def test_build_offer_metric_cubes_rising_three_variant():
    rec = {
        "symbol": "CLF",
        "strategy": "rising_three_methods",
        "strategy_id": "rising_three_methods",
        "entry_policy": "market_open",
        "pattern_weak": True,
        "pattern_score": 8.5,
        "score": 11.0,
        "vol_ratio": 0.5,
        "volume_ok": False,
    }
    cubes = build_offer_metric_cubes(rec, rank=3)
    by_title = {c["title"]: c for c in cubes}
    assert "שיטת כניסה" in by_title
    assert "Rising Three" in by_title["שיטת כניסה"]["value"]
    assert "תבנית Rising Three" in by_title
    assert "ציון ותנודתיות" not in by_title
    rt = by_title["תבנית Rising Three"]
    assert "זיהוי תבנית נרות" in rt["blurb"]
    assert "דירוג #3" in rt["value"]
    assert "(חלש)" in rt["value"]
    assert "8.5" in rt["value"]
    assert rt.get("wide") == "1"


def test_format_offer_prompt_is_short_action_strip():
    text = format_offer_prompt(
        {
            "symbol": "RBLX",
            "score": 13.0,
            "explanation": "WALL OF TEXT SHOULD NOT APPEAR",
            "strategy_id": "score_momentum",
            "entry_policy": "market_open",
        },
        cash_free=1000.0,
        suggested_usd=200.0,
        position_no=1,
        total=5,
    )
    assert "הצעה 1/5" in text
    assert "RBLX" in text
    assert "שיטת כניסה" in text
    assert "מומנטום" in text
    assert "איך לבצע" in text
    assert "דלג" in text
    assert "WALL OF TEXT" not in text


def test_build_offer_action_cubes_merges_cash_swap_and_howto():
    cubes = build_offer_action_cubes(
        {"symbol": "SOXL", "score": 11.4},
        cash_free=0.0,
        suggested_usd=0.0,
        swap={"from_symbol": "PBF", "from_score": 5.9},
    )
    titles = [c["title"] for c in cubes]
    assert titles == ["מזומן וקנייה", "החלפה מומלצת", "איך לבצע"]
    assert "$0" in cubes[0]["value"]
    assert "החלף PBF SOXL" in cubes[1]["value"]
    assert "דלג" in cubes[2]["value"]
    assert "כן / קנה" not in cubes[2]["value"]


def test_format_offer_prompt_zero_cash_with_swap_recommends_swap_command():
    swap = {
        "from_symbol": "AMD",
        "to_symbol": "NVDA",
        "from_score": 6.0,
        "to_score": 14.0,
        "capital_usd": 200.0,
        "pnl_pct": 2.0,
    }
    text = format_offer_prompt(
        {"symbol": "NVDA", "score": 14.0, "strategy_id": "score_momentum"},
        cash_free=0.0,
        suggested_usd=0.0,
        position_no=1,
        total=2,
        swap=swap,
    )
    assert "מזומן פנוי: <b>$0</b>" in text
    assert "מומלץ להחליף" in text
    assert "<code>החלף AMD NVDA</code>" in text
    assert "ממזומן" not in text  # no cash-buy path
    assert "אין מימון מתאים" not in text
    assert "דלג" in text


def test_format_offer_prompt_with_cash_and_swap_shows_both_paths():
    swap = {
        "from_symbol": "AMD",
        "to_symbol": "NVDA",
        "from_score": 6.0,
        "to_score": 14.0,
        "capital_usd": 200.0,
        "pnl_pct": 2.0,
    }
    text = format_offer_prompt(
        {"symbol": "NVDA", "score": 14.0},
        cash_free=300.0,
        suggested_usd=150.0,
        position_no=1,
        total=2,
        swap=swap,
    )
    assert "ממזומן ($150)" in text
    assert "<code>החלף AMD NVDA</code>" in text
    assert "מומלץ להחליף" in text


def test_format_offer_prompt_zero_cash_without_swap_hints_sell():
    text = format_offer_prompt(
        {"symbol": "NVDA", "score": 14.0},
        cash_free=0.0,
        suggested_usd=0.0,
        position_no=1,
        total=1,
        swap=None,
    )
    assert "אין מימון מתאים מהתיק" in text
    assert "מכור SYMBOL" in text
    assert "החלף" not in text


# --------------------------------------------------------------------------
# send_offer
# --------------------------------------------------------------------------


def _patch_send_offer_deps(monkeypatch, *, chart=b"\x89PNG", chart_exc=None, cubes=b"\x89CUBES"):
    from trading_pulse.agent import dryrun_agent as agent
    from trading_pulse.telegram import reply_cards

    photo_calls: list[dict] = []
    notify_calls: list[dict] = []

    def fake_photo(cfg, img, caption, **kwargs):
        photo_calls.append({"img": img, "caption": caption, **kwargs})
        return True

    def fake_notify(cfg, text, context="message", parse_mode=None, **kwargs):
        notify_calls.append({"text": text, "context": context, "parse_mode": parse_mode})
        return True

    def fake_chart(*args, **kwargs):
        if chart_exc:
            raise chart_exc
        return chart

    def fake_cubes(*args, **kwargs):
        return cubes

    monkeypatch.setattr(agent, "send_telegram_photo", fake_photo)
    monkeypatch.setattr(agent, "send_user_notification", fake_notify)
    monkeypatch.setattr(reply_cards, "chart_with_recommendation_details", fake_chart)
    monkeypatch.setattr(reply_cards, "offer_cubes_card", fake_cubes)
    return photo_calls, notify_calls


def test_send_offer_sends_chart_and_cubes_without_second_prompt(monkeypatch):
    photo_calls, notify_calls = _patch_send_offer_deps(monkeypatch)
    state: dict = {}
    plan = _plan()
    start_offer_queue(state, plan)

    assert offer_queue.send_offer(object(), state, plan) is True

    assert len(photo_calls) == 2
    assert photo_calls[0]["caption"] == "#1 NVDA"
    assert "הצעה 1/2" in photo_calls[1]["caption"]
    # Actions live inside the cubes PNG — no separate HTML action message.
    assert notify_calls == []
    po = state["pending_offer"]
    assert po["offered_at"] is not None
    assert po["nudged_at"] is None


def test_send_offer_false_when_no_pending_offer(monkeypatch):
    _patch_send_offer_deps(monkeypatch)
    assert offer_queue.send_offer(object(), {}, _plan()) is False


def test_send_offer_skips_photo_when_chart_missing(monkeypatch):
    photo_calls, notify_calls = _patch_send_offer_deps(monkeypatch, chart=None)
    state: dict = {}
    plan = _plan()
    start_offer_queue(state, plan)

    assert offer_queue.send_offer(object(), state, plan) is True
    assert len(photo_calls) == 1  # cubes card still sent
    assert notify_calls == []


def test_send_offer_swallows_chart_exception_still_sends_cubes(monkeypatch):
    photo_calls, notify_calls = _patch_send_offer_deps(
        monkeypatch, chart_exc=RuntimeError("boom")
    )
    state: dict = {}
    plan = _plan()
    start_offer_queue(state, plan)

    assert offer_queue.send_offer(object(), state, plan) is True
    assert len(photo_calls) == 1  # cubes still sent
    assert "הצעה" in photo_calls[0]["caption"]
    assert notify_calls == []


def test_send_offer_text_fallback_when_cubes_fail(monkeypatch):
    photo_calls, notify_calls = _patch_send_offer_deps(monkeypatch, cubes=None)
    state: dict = {}
    plan = _plan()
    start_offer_queue(state, plan)

    assert offer_queue.send_offer(object(), state, plan) is True
    assert len(photo_calls) == 1  # chart only
    assert len(notify_calls) == 1
    assert "איך לבצע" in notify_calls[0]["text"]


def test_send_offer_skips_forward_when_rec_vanished(monkeypatch):
    photo_calls, notify_calls = _patch_send_offer_deps(monkeypatch)
    state: dict = {}
    plan = _plan()
    start_offer_queue(state, plan)
    # Simulate NVDA rec disappearing from the plan after the queue was seeded.
    plan["recommendations"] = [r for r in plan["recommendations"] if r["symbol"] != "NVDA"]

    assert offer_queue.send_offer(object(), state, plan) is True
    # Should have skipped NVDA and sent the AMD offer instead.
    assert state["pending_offer"]["index"] == 1
    assert notify_calls == []
    assert any("AMD" in (c.get("caption") or "") for c in photo_calls)


def test_send_offer_false_when_all_recs_vanished(monkeypatch):
    _patch_send_offer_deps(monkeypatch)
    state: dict = {}
    plan = _plan()
    start_offer_queue(state, plan)
    plan["recommendations"] = []

    assert offer_queue.send_offer(object(), state, plan) is False


# --------------------------------------------------------------------------
# finish_offers
# --------------------------------------------------------------------------


def test_finish_offers_mentions_approved_symbols(monkeypatch):
    from trading_pulse.agent import dryrun_agent as agent

    notify_calls: list[dict] = []
    monkeypatch.setattr(
        agent,
        "send_user_notification",
        lambda cfg, text, **kw: notify_calls.append({"text": text, **kw}) or True,
    )
    plan = _plan(
        recommendations=[
            {"symbol": "NVDA", "approved": True},
            {"symbol": "AMD", "offer_skipped": True},
        ]
    )
    finish_offers(object(), plan)
    assert len(notify_calls) == 1
    assert "NVDA" in notify_calls[0]["text"]
    assert notify_calls[0]["context"] == "offer:done"


def test_finish_offers_nothing_bought(monkeypatch):
    from trading_pulse.agent import dryrun_agent as agent

    notify_calls: list[dict] = []
    monkeypatch.setattr(
        agent,
        "send_user_notification",
        lambda cfg, text, **kw: notify_calls.append({"text": text, **kw}) or True,
    )
    plan = _plan(recommendations=[{"symbol": "NVDA", "offer_skipped": True}])
    finish_offers(object(), plan)
    assert "לא נקנה כלום היום" in notify_calls[0]["text"]


# --------------------------------------------------------------------------
# start_and_send_first_offer
# --------------------------------------------------------------------------


def test_start_and_send_first_offer_false_when_nothing_to_offer(monkeypatch):
    _patch_send_offer_deps(monkeypatch)
    state: dict = {}
    plan = _plan(recommendations=[])
    assert start_and_send_first_offer(object(), state, plan) is False
    assert "pending_offer" not in state


def test_start_and_send_first_offer_sends_first(monkeypatch):
    photo_calls, notify_calls = _patch_send_offer_deps(monkeypatch)
    state: dict = {}
    plan = _plan()
    assert start_and_send_first_offer(object(), state, plan) is True
    assert notify_calls == []
    assert any("NVDA" in (c.get("caption") or "") for c in photo_calls)
    assert state["pending_offer"]["offered_at"] is not None


# --------------------------------------------------------------------------
# maybe_nudge_offer
# --------------------------------------------------------------------------


def test_maybe_nudge_offer_false_when_no_pending_offer(monkeypatch):
    from trading_pulse.agent import dryrun_agent as agent

    monkeypatch.setattr(agent, "send_user_notification", lambda *a, **k: True)
    assert maybe_nudge_offer(object(), {}) is False


def test_maybe_nudge_offer_false_when_too_recent(monkeypatch):
    from trading_pulse.agent import dryrun_agent as agent

    monkeypatch.setattr(agent, "send_user_notification", lambda *a, **k: True)
    state = {
        "pending_offer": {
            "queue": ["NVDA"],
            "index": 0,
            "offered_at": datetime.now(timezone.utc).isoformat(),
            "nudged_at": None,
        }
    }
    assert maybe_nudge_offer(object(), state) is False


def test_maybe_nudge_offer_false_when_already_nudged(monkeypatch):
    from trading_pulse.agent import dryrun_agent as agent

    monkeypatch.setattr(agent, "send_user_notification", lambda *a, **k: True)
    old = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    state = {
        "pending_offer": {
            "queue": ["NVDA"],
            "index": 0,
            "offered_at": old,
            "nudged_at": old,
        }
    }
    assert maybe_nudge_offer(object(), state) is False


def test_maybe_nudge_offer_sends_after_ten_minutes(monkeypatch):
    from trading_pulse.agent import dryrun_agent as agent

    notify_calls: list[dict] = []
    monkeypatch.setattr(
        agent,
        "send_user_notification",
        lambda cfg, text, **kw: notify_calls.append({"text": text, **kw}) or True,
    )
    old = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    state = {
        "pending_offer": {
            "queue": ["NVDA"],
            "index": 0,
            "offered_at": old,
            "nudged_at": None,
        }
    }
    assert maybe_nudge_offer(object(), state) is True
    assert "NVDA" in notify_calls[0]["text"]
    assert notify_calls[0]["context"] == "offer:nudge"
    assert state["pending_offer"]["nudged_at"] is not None


# --------------------------------------------------------------------------
# expire_stale_offer
# --------------------------------------------------------------------------


def test_expire_stale_offer_false_when_no_pending_offer():
    assert expire_stale_offer({}) is False


def test_expire_stale_offer_false_when_offered_at_missing():
    state = {"pending_offer": {"queue": ["NVDA"], "index": 0, "offered_at": None}}
    assert expire_stale_offer(state) is False
    assert "pending_offer" in state


def test_expire_stale_offer_false_when_within_ttl():
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    state = {"pending_offer": {"queue": ["NVDA"], "index": 0, "offered_at": recent}}
    assert expire_stale_offer(state) is False
    assert "pending_offer" in state


def test_expire_stale_offer_drops_when_past_ttl():
    stale = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    state = {"pending_offer": {"queue": ["NVDA"], "index": 0, "offered_at": stale}}
    assert expire_stale_offer(state) is True
    assert "pending_offer" not in state


# --------------------------------------------------------------------------
# try_resolve_pending_offer
# --------------------------------------------------------------------------


def _setup_try_resolve(monkeypatch, tmp_path, plan: dict):
    from trading_pulse.agent import dryrun_agent as agent

    plan_file = tmp_path / "plan_2026-07-20.json"
    agent.save_json(plan_file, plan)
    state_file = tmp_path / "state.json"

    monkeypatch.setattr(agent, "plan_path", lambda _day: plan_file)
    monkeypatch.setattr(agent, "STATE_FILE", state_file)

    notify_calls: list[dict] = []
    monkeypatch.setattr(
        agent,
        "send_user_notification",
        lambda cfg, text, **kw: notify_calls.append({"text": text, **kw}) or True,
    )

    finish_calls: list[dict] = []
    monkeypatch.setattr(
        offer_queue,
        "finish_offers",
        lambda cfg, p: finish_calls.append(p),
    )
    send_offer_calls: list[dict] = []
    monkeypatch.setattr(
        offer_queue,
        "send_offer",
        lambda cfg, st, p: send_offer_calls.append(p) or True,
    )
    return plan_file, notify_calls, finish_calls, send_offer_calls


def test_try_resolve_pending_offer_false_when_no_pending_offer(monkeypatch):
    assert try_resolve_pending_offer(object(), {}, "כן") is False


def test_try_resolve_pending_offer_false_when_text_not_a_reply(monkeypatch, tmp_path):
    plan = _plan()
    plan_file, notify_calls, *_ = _setup_try_resolve(monkeypatch, tmp_path, plan)
    state: dict = {}
    start_offer_queue(state, plan)

    assert try_resolve_pending_offer(object(), state, "מכור AAPL") is False
    assert notify_calls == []
    assert state["pending_offer"]["index"] == 0  # untouched


@pytest.mark.parametrize("word", ["כן", "אישור", "קנה", "yes"])
def test_try_resolve_pending_offer_buy_with_yes_word(monkeypatch, tmp_path, word):
    plan = _plan(available_capital_usd=300.0)
    plan_file, notify_calls, finish_calls, send_offer_calls = _setup_try_resolve(
        monkeypatch, tmp_path, plan
    )
    state: dict = {}
    start_offer_queue(state, plan)

    assert try_resolve_pending_offer(object(), state, word) is True
    saved = __import__("trading_pulse.agent.dryrun_agent", fromlist=["read_json"]).read_json(
        plan_file
    )
    nvda = next(r for r in saved["recommendations"] if r["symbol"] == "NVDA")
    assert nvda["approved"] is True
    assert nvda["capital_usd"] == 150.0  # equal split of $300 across 2 offers
    assert state["pending_offer"]["decided"]["NVDA"] == 150.0
    assert state["pending_offer"]["index"] == 1
    assert "✅" in notify_calls[0]["text"]
    assert "NVDA" in notify_calls[0]["text"]
    # More offers remain (AMD) — the next offer is sent automatically.
    assert len(send_offer_calls) == 1
    assert finish_calls == []


@pytest.mark.parametrize("word", ["דלג", "skip", "לא"])
def test_try_resolve_pending_offer_skip_word(monkeypatch, tmp_path, word):
    plan = _plan()
    plan_file, notify_calls, finish_calls, send_offer_calls = _setup_try_resolve(
        monkeypatch, tmp_path, plan
    )
    state: dict = {}
    start_offer_queue(state, plan)

    assert try_resolve_pending_offer(object(), state, word) is True
    saved = __import__("trading_pulse.agent.dryrun_agent", fromlist=["read_json"]).read_json(
        plan_file
    )
    nvda = next(r for r in saved["recommendations"] if r["symbol"] == "NVDA")
    assert nvda["approved"] is False
    assert nvda["offer_skipped"] is True
    assert "⏭️" in notify_calls[0]["text"]
    assert len(send_offer_calls) == 1  # AMD offer sent next


@pytest.mark.parametrize("text", ["150", "$150", "150.0", "1,50"])
def test_try_resolve_pending_offer_bare_amount(monkeypatch, tmp_path, text):
    plan = _plan(available_capital_usd=300.0)
    plan_file, notify_calls, *_ = _setup_try_resolve(monkeypatch, tmp_path, plan)
    state: dict = {}
    start_offer_queue(state, plan)

    assert try_resolve_pending_offer(object(), state, text) is True
    saved = __import__("trading_pulse.agent.dryrun_agent", fromlist=["read_json"]).read_json(
        plan_file
    )
    nvda = next(r for r in saved["recommendations"] if r["symbol"] == "NVDA")
    assert nvda["approved"] is True
    # "1,50" parses to 150 once commas are stripped, matching the others.
    assert nvda["capital_usd"] == 150.0


@pytest.mark.parametrize("text", ["קנה 200", "תקנה 200", "buy $200", "קנה NVDA 200"])
def test_try_resolve_pending_offer_buy_amount_phrase(monkeypatch, tmp_path, text):
    """Users naturally type `קנה 200` — must count as amount for the open offer."""
    plan = _plan(available_capital_usd=1000.0)
    plan_file, notify_calls, *_ = _setup_try_resolve(monkeypatch, tmp_path, plan)
    state: dict = {}
    start_offer_queue(state, plan)

    assert try_resolve_pending_offer(object(), state, text) is True
    saved = __import__("trading_pulse.agent.dryrun_agent", fromlist=["read_json"]).read_json(
        plan_file
    )
    nvda = next(r for r in saved["recommendations"] if r["symbol"] == "NVDA")
    assert nvda["approved"] is True
    assert nvda["capital_usd"] == 200.0
    assert "נקנה" in notify_calls[0]["text"]


def test_try_resolve_pending_offer_buy_other_symbol_falls_through(monkeypatch, tmp_path):
    plan = _plan(available_capital_usd=1000.0)
    plan_file, notify_calls, *_ = _setup_try_resolve(monkeypatch, tmp_path, plan)
    state: dict = {}
    start_offer_queue(state, plan)

    assert try_resolve_pending_offer(object(), state, "קנה AAPL 200") is False
    assert notify_calls == []
    assert state["pending_offer"]["index"] == 0


def test_try_resolve_pending_offer_amount_clamped_to_cash_remaining(monkeypatch, tmp_path):
    plan = _plan(available_capital_usd=100.0)
    plan_file, *_ = _setup_try_resolve(monkeypatch, tmp_path, plan)
    state: dict = {}
    start_offer_queue(state, plan)

    assert try_resolve_pending_offer(object(), state, "9999") is True
    saved = __import__("trading_pulse.agent.dryrun_agent", fromlist=["read_json"]).read_json(
        plan_file
    )
    nvda = next(r for r in saved["recommendations"] if r["symbol"] == "NVDA")
    assert nvda["capital_usd"] == 100.0


@pytest.mark.parametrize("text", ["0", "-10", "not a number", ""])
def test_try_resolve_pending_offer_rejects_invalid_amount(monkeypatch, tmp_path, text):
    plan = _plan()
    plan_file, notify_calls, *_ = _setup_try_resolve(monkeypatch, tmp_path, plan)
    state: dict = {}
    start_offer_queue(state, plan)

    assert try_resolve_pending_offer(object(), state, text) is False
    assert notify_calls == []
    assert state["pending_offer"]["index"] == 0


def test_try_resolve_pending_offer_finishes_queue_when_last_offer_decided(
    monkeypatch, tmp_path
):
    plan = _plan(
        available_capital_usd=200.0,
        recommendations=[{"symbol": "NVDA", "score": 14.0}],
    )
    plan_file, notify_calls, finish_calls, send_offer_calls = _setup_try_resolve(
        monkeypatch, tmp_path, plan
    )
    state: dict = {}
    start_offer_queue(state, plan)

    assert try_resolve_pending_offer(object(), state, "כן") is True
    assert "pending_offer" not in state
    assert send_offer_calls == []  # no more offers to send
    assert len(finish_calls) == 1
    saved = __import__("trading_pulse.agent.dryrun_agent", fromlist=["read_json"]).read_json(
        plan_file
    )
    assert saved["status"] == "confirmed"


def test_try_resolve_yes_with_zero_cash_stays_on_offer_and_hints_swap(
    monkeypatch, tmp_path
):
    plan = _plan(
        available_capital_usd=0.0,
        holdings=[{"symbol": "AMD", "capital_usd": 200}],
        holding_actions=[
            {
                "symbol": "AMD",
                "verdict": "swap",
                "swap_to": "NVDA",
                "score": 6.0,
                "pnl_pct": 2.0,
                "capital_usd": 200,
            }
        ],
        recommendations=[
            {"symbol": "NVDA", "score": 14.0},
            {"symbol": "AMD", "score": 10.0},
        ],
    )
    plan_file, notify_calls, finish_calls, send_offer_calls = _setup_try_resolve(
        monkeypatch, tmp_path, plan
    )
    state: dict = {}
    start_offer_queue(state, plan)
    assert current_offer_symbol(state) == "NVDA"

    assert try_resolve_pending_offer(object(), state, "כן") is True
    assert state["pending_offer"]["index"] == 0  # did not advance
    assert "NVDA" not in state["pending_offer"]["decided"]
    assert notify_calls[0]["context"] == "offer:needs_swap"
    assert "אין מזומן פנוי" in notify_calls[0]["text"]
    assert "החלף AMD NVDA" in notify_calls[0]["text"]
    assert send_offer_calls == []
    assert finish_calls == []
    saved = __import__("trading_pulse.agent.dryrun_agent", fromlist=["read_json"]).read_json(
        plan_file
    )
    nvda = next(r for r in saved["recommendations"] if r["symbol"] == "NVDA")
    assert not nvda.get("approved")


def test_try_resolve_yes_with_zero_cash_no_swap_hints_sell(monkeypatch, tmp_path):
    plan = _plan(
        available_capital_usd=0.0,
        holdings=[{"symbol": "META", "capital_usd": 250}],
        holding_actions=[
            {"symbol": "META", "verdict": "hold", "score": 13.0, "pnl_pct": 1.0},
        ],
        recommendations=[{"symbol": "NVDA", "score": 14.0}],
    )
    plan_file, notify_calls, finish_calls, send_offer_calls = _setup_try_resolve(
        monkeypatch, tmp_path, plan
    )
    state: dict = {}
    start_offer_queue(state, plan)

    assert try_resolve_pending_offer(object(), state, "כן") is True
    assert state["pending_offer"]["index"] == 0
    assert notify_calls[0]["context"] == "offer:no_cash"
    assert "מכור SYMBOL" in notify_calls[0]["text"]
    assert send_offer_calls == []
    assert finish_calls == []


def test_try_resolve_pending_offer_pops_state_when_plan_missing(monkeypatch, tmp_path):
    from trading_pulse.agent import dryrun_agent as agent

    missing = tmp_path / "missing.json"
    monkeypatch.setattr(agent, "plan_path", lambda _day: missing)
    state = {
        "pending_offer": {
            "trading_day": "2026-07-20",
            "queue": ["NVDA"],
            "index": 0,
            "decided": {},
            "offered_at": None,
            "nudged_at": None,
        }
    }
    assert try_resolve_pending_offer(object(), state, "כן") is False
    assert "pending_offer" not in state


def test_try_resolve_pending_offer_pops_state_when_trading_day_invalid(monkeypatch):
    state = {
        "pending_offer": {
            "trading_day": "not-a-date",
            "queue": ["NVDA"],
            "index": 0,
            "decided": {},
            "offered_at": None,
            "nudged_at": None,
        }
    }
    assert try_resolve_pending_offer(object(), state, "כן") is False
    assert "pending_offer" not in state


# --------------------------------------------------------------------------
# cutoff_pending_offer
# --------------------------------------------------------------------------


def test_cutoff_pending_offer_false_when_no_pending_offer():
    assert offer_queue.cutoff_pending_offer(object(), {}) is False


def test_cutoff_pending_offer_marks_remaining_skipped_and_finalizes(monkeypatch, tmp_path):
    from trading_pulse.agent import dryrun_agent as agent

    plan = _plan(available_capital_usd=300.0)
    plan_file = tmp_path / "plan_2026-07-20.json"
    agent.save_json(plan_file, plan)
    monkeypatch.setattr(agent, "plan_path", lambda _day: plan_file)

    notify_calls: list[dict] = []
    monkeypatch.setattr(
        agent,
        "send_user_notification",
        lambda cfg, text, **kw: notify_calls.append({"text": text, **kw}) or True,
    )

    state = {
        "pending_offer": {
            "trading_day": "2026-07-20",
            "queue": ["NVDA", "AMD"],
            "index": 0,
            "decided": {},
            "offered_at": datetime.now(timezone.utc).isoformat(),
            "nudged_at": None,
        }
    }
    assert offer_queue.cutoff_pending_offer(object(), state) is True
    assert "pending_offer" not in state

    saved = agent.read_json(plan_file)
    for sym in ("NVDA", "AMD"):
        rec = next(r for r in saved["recommendations"] if r["symbol"] == sym)
        assert rec["offer_skipped"] is True
        assert rec["approved"] is False
    assert saved["status"] == "draft"  # nothing approved
    assert len(notify_calls) == 1
    assert "NVDA" in notify_calls[0]["text"]
    assert "AMD" in notify_calls[0]["text"]
    assert notify_calls[0]["context"] == "offer:cutoff"


def test_cutoff_pending_offer_no_notification_when_nothing_remaining(monkeypatch, tmp_path):
    from trading_pulse.agent import dryrun_agent as agent

    plan = _plan()
    plan_file = tmp_path / "plan_2026-07-20.json"
    agent.save_json(plan_file, plan)
    monkeypatch.setattr(agent, "plan_path", lambda _day: plan_file)

    notify_calls: list[dict] = []
    monkeypatch.setattr(
        agent,
        "send_user_notification",
        lambda cfg, text, **kw: notify_calls.append({"text": text, **kw}) or True,
    )

    state = {
        "pending_offer": {
            "trading_day": "2026-07-20",
            "queue": ["NVDA", "AMD"],
            "index": 2,  # already fully decided
            "decided": {"NVDA": 100.0, "AMD": 100.0},
            "offered_at": None,
            "nudged_at": None,
        }
    }
    assert offer_queue.cutoff_pending_offer(object(), state) is True
    assert "pending_offer" not in state
    assert notify_calls == []


def test_cutoff_pending_offer_clears_state_when_plan_file_missing(monkeypatch, tmp_path):
    from trading_pulse.agent import dryrun_agent as agent

    missing = tmp_path / "missing.json"
    monkeypatch.setattr(agent, "plan_path", lambda _day: missing)
    state = {
        "pending_offer": {
            "trading_day": "2026-07-20",
            "queue": ["NVDA"],
            "index": 0,
            "decided": {},
            "offered_at": None,
            "nudged_at": None,
        }
    }
    assert offer_queue.cutoff_pending_offer(object(), state) is True
    assert "pending_offer" not in state


def test_cutoff_pending_offer_clears_state_when_trading_day_invalid():
    state = {
        "pending_offer": {
            "trading_day": "not-a-date",
            "queue": ["NVDA"],
            "index": 0,
            "decided": {},
            "offered_at": None,
            "nudged_at": None,
        }
    }
    assert offer_queue.cutoff_pending_offer(object(), state) is True
    assert "pending_offer" not in state
