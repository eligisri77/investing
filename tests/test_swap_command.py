"""Tests for intraday swap (sell + buy symbol not in evening plan)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import trading_pulse.agent.dryrun_agent as agent


@dataclass
class Cfg:
    stop_loss_pct: float = 0.12
    take_profit_pct: float = 0.25
    max_open_positions: int = 4
    commission_per_side_usd: float = 0.0
    entry_sim_time: str = "13:35"
    signal_sources: tuple = ("yahoo",)
    min_signal_sources: int = 1
    min_volume_ratio: float = 0.0
    min_price_usd: float = 0.0
    min_avg_volume_20d: int = 0
    source_weights: dict | None = None
    max_source_score_std: float = 99.0
    max_source_score_spread: float = 99.0
    disagreement_score_penalty: float = 0.0
    exclude_on_source_disagreement: bool = False


def _plan(tmp_path: Path, day: str = "2026-07-08") -> Path:
    plan = {
        "for_trading_day": day,
        "recommendations": [
            {"symbol": "LABD", "approved": True, "capital_usd": 333.0},
            {"symbol": "RIVN", "approved": True, "capital_usd": 333.0},
        ],
    }
    p = tmp_path / "plans" / f"plan_{day}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(__import__("json").dumps(plan), encoding="utf-8")
    return p


def test_swap_buys_intraday_target_not_in_plan(tmp_path, monkeypatch):
    state = {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": "LABD",
                "capital_usd": 333.0,
                "entry_price": 7.0,
                "entry_day": "2026-07-08",
                "stop_loss_pct": 0.12,
                "take_profit_pct": 0.25,
            }
        ],
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(__import__("json").dumps(state), encoding="utf-8")
    _plan(tmp_path)

    monkeypatch.setattr(agent, "STATE_FILE", state_path)
    monkeypatch.setattr(agent, "PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr(agent, "resolve_trading_day", lambda _d: "2026-07-08")
    monkeypatch.setattr(agent, "load_state", lambda _cfg: __import__("json").loads(state_path.read_text()))
    monkeypatch.setattr(
        agent,
        "save_json",
        lambda path, data: path.write_text(__import__("json").dumps(data), encoding="utf-8"),
    )
    monkeypatch.setattr(agent, "fetch_signal_universe", lambda _s, _c: __import__("pandas").DataFrame())
    monkeypatch.setattr(
        agent,
        "_open_position_now",
        lambda _cfg, st, rec, _day: (
            st.setdefault("open_positions", []).append(
                {
                    "symbol": rec["symbol"],
                    "entry_price": 36.5,
                    "capital_usd": rec["capital_usd"],
                }
            )
            or st["open_positions"][-1]
        ),
    )
    def _fake_sell(_cfg, st, sym, frac, **kw):
        st["open_positions"] = [p for p in st.get("open_positions", []) if p["symbol"] != sym.upper()]
        st["equity"] = round(float(st.get("equity", 0)) - 12.0, 2)
        return {
            "symbol": sym,
            "pnl_usd": -12.0,
            "capital_usd": 333.0,
            "exit_price": 6.5,
        }

    monkeypatch.setattr("trading_pulse.agent.positions.partial_sell_position", _fake_sell)
    monkeypatch.setattr(
        "trading_pulse.agent.positions.fetch_day_ohlc",
        lambda sym, day: {"open": 7.0, "high": 7.2, "low": 6.8, "close": 7.1},
    )
    monkeypatch.setattr(
        "trading_pulse.agent.trading_flow.before_market_entry",
        lambda _cfg, _day: False,
    )
    sync_actions: list[str] = []
    monkeypatch.setattr(
        agent,
        "_sync_plan_after_manual_action",
        lambda _cfg, _state, action: sync_actions.append(action),
    )
    sent_cards: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "send_telegram_card",
        lambda *_a, **_k: sent_cards.append((_a, _k)) or True,
    )
    card_kwargs: list[dict] = []
    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_swap",
        lambda **kw: card_kwargs.append(kw) or b"\x89PNG\r\n\x1a\nswap",
    )

    reply = agent.execute_swap_command(Cfg(), "LABD", "BEAM")

    # Cubes PNG goes to Telegram; command reply is empty (same as sell).
    assert reply == ""
    assert sent_cards
    _args, _kwargs = sent_cards[0]
    assert _args[1] == b"\x89PNG\r\n\x1a\nswap"
    assert _args[2] == "החלפה LABD → BEAM"
    assert _args[3] == "reply:swap"
    assert len(card_kwargs) == 1
    assert card_kwargs[0]["from_symbol"] == "LABD"
    assert card_kwargs[0]["to_symbol"] == "BEAM"
    assert card_kwargs[0]["sold_usd"] == 333.0
    assert card_kwargs[0]["sell_price"] == 6.5
    assert card_kwargs[0]["sell_pnl_usd"] == -12.0
    assert card_kwargs[0]["entry_price"] == 36.5

    saved_state = __import__("json").loads(state_path.read_text())
    held = {p["symbol"] for p in saved_state.get("open_positions", [])}
    assert "LABD" not in held
    assert "BEAM" in held

    saved_plan = __import__("json").loads((tmp_path / "plans" / "plan_2026-07-08.json").read_text())
    symbols = [r["symbol"] for r in saved_plan["recommendations"]]
    assert "BEAM" in symbols
    beam = next(r for r in saved_plan["recommendations"] if r["symbol"] == "BEAM")
    assert beam["approved"] is True
    labd = next(r for r in saved_plan["recommendations"] if r["symbol"] == "LABD")
    assert labd["approved"] is False
    assert sync_actions == [
        "מכירה ידנית של LABD כחלק מהחלפה",
        "החלפה ידנית של LABD ב־BEAM",
    ]


def test_swap_partial_usd_does_not_sell_all(tmp_path, monkeypatch):
    """מכור X תקנה Y $100 should sell only $100, not the whole position."""
    state = {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": "LABD",
                "capital_usd": 333.0,
                "entry_price": 7.0,
                "entry_day": "2026-07-08",
                "stop_loss_pct": 0.12,
                "take_profit_pct": 0.25,
            }
        ],
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(__import__("json").dumps(state), encoding="utf-8")
    _plan(tmp_path)

    monkeypatch.setattr(agent, "STATE_FILE", state_path)
    monkeypatch.setattr(agent, "PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr(agent, "resolve_trading_day", lambda _d: "2026-07-08")
    monkeypatch.setattr(agent, "load_state", lambda _cfg: __import__("json").loads(state_path.read_text()))
    monkeypatch.setattr(
        agent,
        "save_json",
        lambda path, data: path.write_text(__import__("json").dumps(data), encoding="utf-8"),
    )
    sold_amounts: list[float] = []

    def _fake_sell_usd(_cfg, st, sym, usd, **kw):
        sold_amounts.append(float(usd))
        for p in st.get("open_positions", []):
            if p["symbol"] == sym.upper():
                p["capital_usd"] = round(float(p["capital_usd"]) - float(usd), 2)
                break
        return {"symbol": sym, "pnl_usd": 0.0, "capital_usd": float(usd)}

    def _fake_sell_full(*_a, **_k):
        raise AssertionError("full sell should not be used when buy_usd is set")

    monkeypatch.setattr("trading_pulse.agent.positions.partial_sell_usd", _fake_sell_usd)
    monkeypatch.setattr("trading_pulse.agent.positions.partial_sell_position", _fake_sell_full)
    monkeypatch.setattr(
        "trading_pulse.agent.trading_flow.before_market_entry",
        lambda _cfg, _day: True,
    )
    monkeypatch.setattr(
        agent,
        "set_plan_status",
        lambda *a, **k: "תוכנית מאושרת",
    )
    sync_actions: list[str] = []
    monkeypatch.setattr(
        agent,
        "_sync_plan_after_manual_action",
        lambda _cfg, _state, action: sync_actions.append(action),
    )

    reply = agent.execute_swap_command(Cfg(), "LABD", "RIVN", buy_usd=100.0)
    assert sold_amounts == [100.0]
    assert "100" in reply
    assert "333" not in reply.split("מכרת")[1].split("\n")[0]
    assert sync_actions == ["מכירה ידנית של LABD כחלק מהחלפה"]
    saved_plan = __import__("json").loads(
        (tmp_path / "plans" / "plan_2026-07-08.json").read_text()
    )
    assert saved_plan["last_manual_action"] == "החלפה ידנית של LABD ב־RIVN"
    assert saved_plan["portfolio_snapshot_stale"] is False


def test_swap_rejects_same_symbol():
    reply = agent.execute_swap_command(Cfg(), "BEAM", "BEAM")
    assert reply.startswith("❌")


def test_deliver_swap_completed_sends_card_and_returns_empty(monkeypatch):
    sent: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "send_telegram_card",
        lambda *_a, **_k: sent.append((_a, _k)) or True,
    )
    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_swap",
        lambda **kw: b"\x89PNG\r\n\x1a\ncubes",
    )
    monkeypatch.setattr(
        "trading_pulse.telegram.app_notify.uses_app_notifications",
        lambda _cfg: False,
    )

    out = agent._deliver_swap_completed(
        Cfg(),
        from_symbol="LABD",
        to_symbol="BEAM",
        sold_usd=333.0,
        bought_usd=320.0,
        buy_price=36.5,
        cash=13.0,
        holdings=[{"symbol": "BEAM", "capital_usd": 320}],
        sell_price=6.5,
        sell_pnl_usd=-12.0,
    )
    assert out == ""
    assert len(sent) == 1
    assert sent[0][0][1] == b"\x89PNG\r\n\x1a\ncubes"
    assert sent[0][0][2] == "החלפה LABD → BEAM"
    assert sent[0][0][3] == "reply:swap"


def test_deliver_swap_completed_falls_back_to_html_on_card_error(monkeypatch):
    monkeypatch.setattr(
        agent,
        "send_telegram_card",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("telegram down")),
    )
    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_swap",
        lambda **kw: b"\x89PNG\r\n\x1a\ncubes",
    )

    out = agent._deliver_swap_completed(
        Cfg(),
        from_symbol="LABD",
        to_symbol="BEAM",
        sold_usd=200.0,
        bought_usd=180.0,
        buy_price=36.0,
        cash=20.0,
        holdings=[],
        sell_price=6.5,
        sell_pnl_usd=-5.0,
    )
    assert "החלפה הושלמה" in out
    assert "מכרת LABD" in out
    assert "קנית BEAM" in out
    assert "ערך <b>$200.00</b>" in out
    assert "הפסד <b>-$5.00</b>" in out


def test_deliver_swap_completed_notifies_app_inbox(monkeypatch):
    monkeypatch.setattr(agent, "send_telegram_card", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_swap",
        lambda **kw: b"\x89PNG\r\n\x1a\ncubes",
    )
    monkeypatch.setattr(
        "trading_pulse.telegram.app_notify.uses_app_notifications",
        lambda _cfg: True,
    )
    inbox: list[tuple] = []
    monkeypatch.setattr(
        "trading_pulse.telegram.app_notify.notify_user",
        lambda cfg, html, kind, **kw: inbox.append((html, kind, kw)),
    )

    out = agent._deliver_swap_completed(
        Cfg(),
        from_symbol="PBF",
        to_symbol="CDNA",
        sold_usd=200.0,
        bought_usd=47.65,
        buy_price=209.0,
        cash=0.0,
        holdings=[],
        sell_price=12.5,
        sell_pnl_usd=3.0,
    )
    assert out == ""
    assert len(inbox) == 1
    html, kind, kw = inbox[0]
    assert kind == "reply:swap"
    assert kw.get("parse_mode") == "HTML"
    assert kw.get("telegram_sender") is False
    assert "החלפה הושלמה" in html
    assert "רווח <b>+$3.00</b>" in html


def test_swap_clears_price_watch_for_sold_symbol(tmp_path, monkeypatch):
    """Full swap sell removes Method2 / hourly watch on the sold symbol."""
    from trading_pulse.agent.price_watch import add_price_watch, list_price_watches

    state = {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": "LABD",
                "capital_usd": 333.0,
                "entry_price": 7.0,
                "entry_day": "2026-07-08",
                "stop_loss_pct": 0.12,
                "take_profit_pct": 0.25,
            }
        ],
    }
    add_price_watch(state, "LABD")
    add_price_watch(state, "NVDA")
    state_path = tmp_path / "state.json"
    state_path.write_text(__import__("json").dumps(state), encoding="utf-8")
    _plan(tmp_path)

    monkeypatch.setattr(agent, "STATE_FILE", state_path)
    monkeypatch.setattr(agent, "PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr(agent, "resolve_trading_day", lambda _d: "2026-07-08")
    monkeypatch.setattr(
        agent,
        "load_state",
        lambda _cfg: __import__("json").loads(state_path.read_text()),
    )
    monkeypatch.setattr(
        agent,
        "save_json",
        lambda path, data: path.write_text(
            __import__("json").dumps(data), encoding="utf-8"
        ),
    )
    monkeypatch.setattr(
        agent, "fetch_signal_universe", lambda _s, _c: __import__("pandas").DataFrame()
    )
    monkeypatch.setattr(
        agent,
        "_open_position_now",
        lambda _cfg, st, rec, _day: (
            st.setdefault("open_positions", []).append(
                {
                    "symbol": rec["symbol"],
                    "entry_price": 36.5,
                    "capital_usd": rec["capital_usd"],
                }
            )
            or st["open_positions"][-1]
        ),
    )

    def _fake_sell(_cfg, st, sym, frac, **kw):
        st["open_positions"] = [
            p for p in st.get("open_positions", []) if p["symbol"] != sym.upper()
        ]
        return {"symbol": sym, "pnl_usd": -12.0, "capital_usd": 333.0}

    monkeypatch.setattr("trading_pulse.agent.positions.partial_sell_position", _fake_sell)
    monkeypatch.setattr(
        "trading_pulse.agent.positions.fetch_day_ohlc",
        lambda sym, day: {"open": 7.0, "high": 7.2, "low": 6.8, "close": 7.1},
    )
    monkeypatch.setattr(
        "trading_pulse.agent.trading_flow.before_market_entry",
        lambda _cfg, _day: False,
    )
    monkeypatch.setattr(agent, "_sync_plan_after_manual_action", lambda *_a: None)
    monkeypatch.setattr(agent, "send_telegram_card", lambda *_a, **_k: True)

    agent.execute_swap_command(Cfg(), "LABD", "BEAM")

    saved = __import__("json").loads(state_path.read_text())
    assert "LABD" not in list_price_watches(saved)
    assert "NVDA" in list_price_watches(saved)
