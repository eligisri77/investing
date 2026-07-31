"""Tests for the sequential one-at-a-time buy-offer state machine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trading_pulse.agent import offer_queue
from trading_pulse.agent.offer_queue import (
    cash_remaining,
    current_offer_symbol,
    eligible_offer_symbols,
    expire_stale_offer,
    finish_offers,
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


# --------------------------------------------------------------------------
# send_offer
# --------------------------------------------------------------------------


def _patch_send_offer_deps(monkeypatch, *, chart=b"\x89PNG", chart_exc=None):
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

    monkeypatch.setattr(agent, "send_telegram_photo", fake_photo)
    monkeypatch.setattr(agent, "send_user_notification", fake_notify)
    monkeypatch.setattr(reply_cards, "chart_with_recommendation_details", fake_chart)
    return photo_calls, notify_calls


def test_send_offer_sends_photo_and_prompt(monkeypatch):
    photo_calls, notify_calls = _patch_send_offer_deps(monkeypatch)
    state: dict = {}
    plan = _plan()
    start_offer_queue(state, plan)

    assert offer_queue.send_offer(object(), state, plan) is True

    assert len(photo_calls) == 1
    assert photo_calls[0]["caption"] == "#1 NVDA"
    assert len(notify_calls) == 1
    text = notify_calls[0]["text"]
    assert "NVDA" in text
    assert "הצעה 1/2" in text
    assert notify_calls[0]["parse_mode"] == "HTML"
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
    assert photo_calls == []
    assert len(notify_calls) == 1


def test_send_offer_swallows_chart_exception(monkeypatch):
    photo_calls, notify_calls = _patch_send_offer_deps(
        monkeypatch, chart_exc=RuntimeError("boom")
    )
    state: dict = {}
    plan = _plan()
    start_offer_queue(state, plan)

    assert offer_queue.send_offer(object(), state, plan) is True
    assert photo_calls == []
    assert len(notify_calls) == 1  # text prompt still sent


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
    assert len(notify_calls) == 1
    assert "AMD" in notify_calls[0]["text"]


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
    assert len(notify_calls) == 1
    assert "NVDA" in notify_calls[0]["text"]


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
