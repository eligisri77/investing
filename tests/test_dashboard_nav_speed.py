"""Dashboard / nav must not Yahoo-fetch every skipped pick."""

from __future__ import annotations

from unittest.mock import patch

from trading_pulse.api import web_app


def test_build_pick_record_skips_hypothetical_by_default():
    plan = {"for_trading_day": "2026-08-01", "recommendations": []}
    rec = {
        "symbol": "AAA",
        "approved": False,
        "capital_usd": 100,
        "stop_loss_pct": 0.1,
        "take_profit_pct": 0.2,
        "entry_ref_price": 10,
        "score": 1,
    }
    with patch.object(web_app, "load_report", return_value=None), patch.object(
        web_app, "hypothetical_trade"
    ) as hypo:
        pick = web_app.build_pick_record(plan, rec)
    assert pick["hypothetical_if_skipped"] is None
    hypo.assert_not_called()


def test_build_pick_record_can_include_hypothetical():
    plan = {"for_trading_day": "2026-08-01"}
    rec = {"symbol": "AAA", "approved": False, "capital_usd": 100}
    fake = {"pnl_usd": 1.0, "hypothetical": True}
    with patch.object(web_app, "load_report", return_value=None), patch.object(
        web_app, "hypothetical_trade", return_value=fake
    ):
        pick = web_app.build_pick_record(plan, rec, include_hypothetical=True)
    assert pick["hypothetical_if_skipped"] == fake


def test_api_nav_is_lightweight(tmp_path, monkeypatch):
    state = {
        "equity": 900.0,
        "open_positions": [{"symbol": "ARKG"}, {"symbol": "cdna"}],
        "history": [],
    }
    monkeypatch.setattr(web_app, "load_state", lambda: state)
    monkeypatch.setattr(web_app, "inbox_summary", lambda: {"unread": 0})
    with patch.object(web_app, "hypothetical_trade") as hypo:
        out = web_app.api_nav()
    assert out["symbols"] == ["ARKG", "CDNA"]
    assert out["inbox"]["unread"] == 0
    hypo.assert_not_called()


def _skipped_pick(symbol: str = "AAA", day: str = "2026-08-01") -> dict:
    return {
        "symbol": symbol,
        "trading_day": day,
        "approved": False,
        "invested": False,
        "trade": None,
        "hypothetical_if_skipped": None,
        "capital_usd": 50,
        "score": 1.0,
        "stop_loss_pct": 0.1,
        "take_profit_pct": 0.2,
    }


def test_api_dashboard_does_not_hypo_every_pick(monkeypatch):
    picks = [_skipped_pick(f"S{i}") for i in range(20)]
    monkeypatch.setattr(web_app, "load_state", lambda: {"equity": 1000, "history": []})
    monkeypatch.setattr(web_app, "load_config", lambda: {"initial_capital": 1000, "monthly_target_usd": 2000})
    monkeypatch.setattr(web_app, "load_all_picks", lambda **kw: list(picks))
    monkeypatch.setattr(web_app, "inbox_summary", lambda: {})
    calls = {"n": 0}

    def _hypo(rec, day):
        calls["n"] += 1
        return {"pnl_usd": 1.0, "pnl_pct": 1.0, "hypothetical": True}

    monkeypatch.setattr(web_app, "hypothetical_trade", _hypo)
    out = web_app.api_dashboard()
    assert out["total_picks"] == 20
    assert len(out["recent_picks"]) == 12
    assert calls["n"] == 12  # only recent slice, not full history
    assert out["recent_picks"][0]["hypothetical_if_skipped"]["pnl_usd"] == 1.0
    assert out["recent_picks"][-1]["hypothetical_if_skipped"]["pnl_usd"] == 1.0


def test_enrich_picks_hypothetical_skips_invested_and_respects_limit():
    picks = [
        {**_skipped_pick("HOLD"), "invested": True, "trade": {"pnl_usd": 2.0}},
        _skipped_pick("A"),
        _skipped_pick("B"),
        _skipped_pick("C"),
    ]
    calls: list[str] = []

    def _hypo(rec, day):
        calls.append(rec["symbol"])
        return {"pnl_usd": 1.0, "hypothetical": True}

    with patch.object(web_app, "hypothetical_trade", side_effect=_hypo):
        web_app.enrich_picks_hypothetical(picks, limit=2)

    assert calls == ["A", "B"]
    assert picks[0]["hypothetical_if_skipped"] is None
    assert picks[1]["hypothetical_if_skipped"]["pnl_usd"] == 1.0
    assert picks[2]["hypothetical_if_skipped"]["pnl_usd"] == 1.0
    assert picks[3]["hypothetical_if_skipped"] is None


def test_api_stock_enriches_symbol_picks(monkeypatch):
    picks = [
        _skipped_pick("AAA", "2026-08-02"),
        _skipped_pick("BBB", "2026-08-02"),
        _skipped_pick("AAA", "2026-08-01"),
    ]
    monkeypatch.setattr(web_app, "load_all_picks", lambda **kw: list(picks))
    calls: list[str] = []

    def _hypo(rec, day):
        calls.append(f"{rec['symbol']}:{day}")
        return {"pnl_usd": 3.0, "hypothetical": True}

    monkeypatch.setattr(web_app, "hypothetical_trade", _hypo)
    out = web_app.api_stock("aaa")
    assert out["symbol"] == "AAA"
    assert len(out["picks"]) == 2
    assert calls == ["AAA:2026-08-02", "AAA:2026-08-01"]
    assert out["stats"]["skipped_hypothetical_pnl_usd"] == 6.0


def test_api_picks_does_not_call_hypothetical(monkeypatch):
    monkeypatch.setattr(
        web_app,
        "load_all_picks",
        lambda **kw: [_skipped_pick()],
    )
    with patch.object(web_app, "hypothetical_trade") as hypo:
        # Route uses default load_all_picks() — no Yahoo enrichment.
        out = web_app.api_picks()
    assert len(out) == 1
    hypo.assert_not_called()
