"""Tests for Telegram reply cards."""

from __future__ import annotations

import pytest

from trading_pulse.telegram.reply_cards import (
    card_buy,
    card_entry,
    card_from_plan_summary,
    card_help,
    card_sell,
    card_swap,
    chart_with_recommendation_details,
    render_html_message_card,
    render_reply_card,
    stack_png_vertical,
)


def test_render_reply_card_png():
    png = render_reply_card(
        "בדיקה",
        accent="cyan",
        rows=[("מזומן", "$20"), ("מניה", "RIVN")],
        bullets=["שורה אחת"],
        chips=["תיק"],
        footer="הערה",
    )
    assert png.startswith(b"\x89PNG")


def test_html_message_card_strips_tags():
    png = render_html_message_card(
        "✅ <b>מכרת RIVN</b> (6%)\nמזומן פנוי: <b>$23</b>",
        accent="green",
    )
    assert png.startswith(b"\x89PNG")


def test_html_message_card_wraps_long_reminder_title():
    from trading_pulse.telegram.telegram_format import format_pre_sim_reminder

    png = render_html_message_card(format_pre_sim_reminder(19, "approval"))
    assert png.startswith(b"\x89PNG")
    # Wrapped title needs more height than a single title line (~120px).
    from io import BytesIO

    from PIL import Image

    h = Image.open(BytesIO(png)).size[1]
    assert h >= 160


def test_trade_cards():
    assert card_sell("RIVN", fraction=0.06, pnl_usd=3.13, cash=23, sold_usd=20).startswith(b"\x89PNG")
    assert card_buy("LABD", bought_usd=20, entry_price=7.1, cash=3).startswith(b"\x89PNG")
    assert card_swap(
        from_symbol="RIVN",
        to_symbol="BEAM",
        sold_usd=200,
        bought_usd=200,
        entry_price=36.0,
        cash=0,
    ).startswith(b"\x89PNG")
    assert card_help().startswith(b"\x89PNG")
    assert card_entry(
        [{"symbol": "BEAM", "capital_usd": 320, "entry_price": 36.6}],
        trading_day="2026-07-09",
    ).startswith(b"\x89PNG")


@pytest.mark.parametrize(
    ("pnl_usd", "outcome", "amount", "accent"),
    [
        (-3.25, "הפסד ממומש", "-$3.25", "red"),
        (3.25, "רווח ממומש", "+$3.25", "green"),
        (0.0, "רווח ממומש", "$0.00", "green"),
    ],
)
def test_sell_card_preserves_sign_and_names_outcome(
    monkeypatch, pnl_usd, outcome, amount, accent
):
    captured = {}

    def fake_render(title, **kwargs):
        captured.update(title=title, **kwargs)
        return b"png"

    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.render_reply_card",
        fake_render,
    )

    assert (
        card_sell(
            "RIVN",
            fraction=0.5,
            pnl_usd=pnl_usd,
            cash=120,
            equity=996.75,
        )
        == b"png"
    )
    assert (outcome, amount) in captured["rows"]
    assert ("הון לאחר המכירה", "$996.75") in captured["rows"]
    assert captured["accent"] == accent


def test_portfolio_card():
    from trading_pulse.telegram.reply_cards import card_portfolio

    png = card_portfolio(
        {
            "equity": 986.68,
            "cash_usd": 20,
            "open_marked_usd": 1021,
            "unrealized_pnl_usd": 34,
            "total_realized_pnl": -13.32,
            "open_positions": [
                {
                    "symbol": "LABD",
                    "status": "holding",
                    "capital_usd": 333,
                    "entry_price": 7.1,
                    "marked_value_usd": 322,
                    "unrealized_pnl_usd": -11,
                    "entry_at": "2026-07-08T17:20:00+00:00",
                },
                {
                    "symbol": "RIVN",
                    "status": "holding",
                    "capital_usd": 333,
                    "entry_price": 15.66,
                    "marked_value_usd": 386,
                    "unrealized_pnl_usd": 52,
                    "entry_at": "2026-07-08T17:20:00+00:00",
                },
            ],
        }
    )
    assert png.startswith(b"\x89PNG")


def test_plan_summary_card():
    plan = {
        "for_trading_day": "2026-07-10",
        "available_capital_usd": 20,
        "deployed_capital_usd": 966,
        "equity_snapshot": 986,
        "holdings": [{"symbol": "LABD", "capital_usd": 333}],
        "recommendations": [{"symbol": "NVDA", "capital_usd": 20}],
        "holding_actions": [{"symbol": "LABD", "verdict": "hold", "pnl_pct": 1.2}],
    }
    png = card_from_plan_summary(plan)
    assert png.startswith(b"\x89PNG")
    assert len(png) > 2000


def test_daily_report_card_squares():
    from trading_pulse.telegram.reply_cards import card_daily_report

    png = card_daily_report(
        {
            "trading_day": "2026-07-22",
            "equity_before": 993.59,
            "equity_after": 991.52,
            "pnl_usd": -2.07,
            "unrealized_pnl_usd": -24.38,
            "equity_marked_usd": 967.14,
            "held_eod": [
                {
                    "symbol": "LCID",
                    "capital_usd": 116,
                    "days_held": 3,
                    "unrealized_pnl_usd": -4.77,
                    "unrealized_pnl_pct": -4.1,
                    "strategy_id": "score",
                }
            ],
            "executed": [
                {
                    "symbol": "VLO",
                    "pnl_usd": -2.07,
                    "pnl_pct": -1.4,
                    "days_held": 0,
                    "exit_reason": "user_sell",
                    "manual_exit": True,
                    "strategy": "method2",
                    "trigger": "2-2-2",
                }
            ],
        }
    )
    assert png.startswith(b"\x89PNG")
    assert len(png) > 3000


def test_entry_card_multi_stock_squares():
    png = card_entry(
        [
            {"symbol": "MPC", "capital_usd": 296, "entry_price": 319.0, "strategy_id": "relative_strength"},
            {"symbol": "ARWR", "capital_usd": 147, "entry_price": 89.25, "strategy_id": "score"},
        ],
        trading_day="2026-07-22",
    )
    assert png.startswith(b"\x89PNG")


def test_heartbeat_card_png():
    from trading_pulse.agent.dryrun_agent import AgentConfig, apply_risk_profile
    from trading_pulse.telegram.reply_cards import card_heartbeat

    cfg = AgentConfig()
    cfg.risk_profile = "speculative"
    apply_risk_profile(cfg)
    png = card_heartbeat(
        cfg,
        {"equity": 969.81, "month_start_equity": 1000.0, "open_positions": []},
        market_day=True,
    )
    assert png.startswith(b"\x89PNG")
    assert len(png) > 2000


def test_allocation_prompt_card_stock_chips():
    from trading_pulse.telegram.reply_cards import card_allocation_prompt

    png = card_allocation_prompt(
        {"equity_snapshot": 970, "recommendations": []},
        [
            {
                "id": 1,
                "title": "שווה",
                "description": "חלוקה שווה",
                "full_invest": True,
                "equity_usd": 970,
                "holdings": [
                    {"symbol": "ISRG", "capital_usd": 116},
                    {"symbol": "NET", "capital_usd": 200},
                ],
                "new_entries": [
                    {"symbol": "CROX", "capital_usd": 106},
                    {"symbol": "CELH", "capital_usd": 106},
                ],
                "deployed_total_usd": 970,
                "reserve_usd": 0,
            },
            {
                "id": 4,
                "title": "חצי",
                "description": "עם מזומן",
                "full_invest": False,
                "equity_usd": 970,
                "holdings": [{"symbol": "ISRG", "capital_usd": 116}],
                "new_entries": [{"symbol": "CROX", "capital_usd": 53}],
                "deployed_total_usd": 859,
                "reserve_usd": 111,
            },
        ],
        trading_day="2026-07-24",
    )
    assert png.startswith(b"\x89PNG")
    assert len(png) > 4000


def _stub_allocation_prompt_deps(monkeypatch, tmp_path, *, options=None):
    """Shared plan/state/options stubs for send_allocation_prompt tests."""
    import json

    plan_file = tmp_path / "plan_2026-07-24.json"
    plan_file.write_text(
        json.dumps({"equity_snapshot": 970, "recommendations": [], "allocation": {}}),
        encoding="utf-8",
    )
    opts = options or [
        {
            "id": 1,
            "title": "שווה",
            "description": "חלוקה שווה",
            "full_invest": True,
            "equity_usd": 970,
            "holdings": [],
            "new_entries": [{"symbol": "CROX", "capital_usd": 200}],
            "deployed_total_usd": 200,
            "reserve_usd": 0,
        }
    ]
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.plan_path",
        lambda _d: plan_file,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.load_state",
        lambda _cfg: {"equity": 970.0, "open_positions": []},
    )
    monkeypatch.setattr(
        "trading_pulse.agent.capital_allocation.ensure_allocation_options",
        lambda *_a, **_k: opts,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.capital_allocation.format_allocation_prompt",
        lambda *_a, **_k: "<b>חלוקת הון</b> בחר ח1",
    )
    return plan_file


def test_send_allocation_prompt_sends_png(tmp_path, monkeypatch):
    from trading_pulse.agent.dryrun_agent import AgentConfig, send_allocation_prompt

    _stub_allocation_prompt_deps(monkeypatch, tmp_path)
    photo_calls: list[dict] = []
    notify_calls: list = []

    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_allocation_prompt",
        lambda *_a, **_k: b"\x89PNG\r\n\x1a\nALLOC",
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_telegram_photo",
        lambda _cfg, img, caption, **kw: photo_calls.append(
            {"img": img, "caption": caption, **kw}
        )
        or True,
    )
    monkeypatch.setattr(
        "trading_pulse.telegram.app_notify.notify_user",
        lambda *_a, **_k: notify_calls.append(True) or True,
    )

    cfg = AgentConfig(notification_mode="telegram")
    assert send_allocation_prompt("2026-07-24", cfg=cfg) is True

    assert len(photo_calls) == 1
    assert photo_calls[0]["caption"] == "חלוקת הון 2026-07-24"
    assert photo_calls[0]["context"] == "allocation:prompt"
    assert photo_calls[0]["img"] == b"\x89PNG\r\n\x1a\nALLOC"
    assert "חלוקת הון" in (photo_calls[0].get("inbox_text") or "")
    assert notify_calls == []


def test_send_allocation_prompt_falls_back_to_html(tmp_path, monkeypatch):
    from trading_pulse.agent.dryrun_agent import AgentConfig, send_allocation_prompt

    _stub_allocation_prompt_deps(monkeypatch, tmp_path)
    notify_calls: list[dict] = []
    photo_calls: list = []

    def _boom(*_a, **_k):
        raise RuntimeError("pillow boom")

    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_allocation_prompt",
        _boom,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_telegram_photo",
        lambda *_a, **_k: photo_calls.append("photo") or True,
    )
    monkeypatch.setattr(
        "trading_pulse.telegram.app_notify.notify_user",
        lambda _cfg, text, context, **kw: notify_calls.append(
            {"text": text, "context": context, **kw}
        )
        or True,
    )

    assert send_allocation_prompt("2026-07-24", cfg=AgentConfig()) is True
    assert photo_calls == []
    assert len(notify_calls) == 1
    assert notify_calls[0]["context"] == "allocation:prompt"
    assert notify_calls[0]["parse_mode"] == "HTML"
    assert "חלוקת הון" in notify_calls[0]["text"]


def test_send_allocation_prompt_missing_plan_returns_false(tmp_path, monkeypatch):
    from trading_pulse.agent.dryrun_agent import AgentConfig, send_allocation_prompt

    missing = tmp_path / "no_plan.json"
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.plan_path",
        lambda _d: missing,
    )
    assert send_allocation_prompt("2026-07-24", cfg=AgentConfig()) is False


def test_send_report_notifications_sends_html_table_card(monkeypatch):
    from trading_pulse.agent.dryrun_agent import AgentConfig, send_report_notifications

    photo_calls: list[dict] = []
    english_table_calls: list = []

    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_daily_report",
        lambda _report: b"\x89PNG\r\n\x1a\nREPORT",
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_telegram_photo",
        lambda _cfg, img, caption, **kw: photo_calls.append(
            {"img": img, "caption": caption, **kw}
        )
        or True,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_report_table_image",
        lambda *_a, **_k: english_table_calls.append(True),
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.format_report_message",
        lambda report: f"<b>דוח</b> {report.get('trading_day')}",
    )

    report = {"trading_day": "2026-07-22", "pnl_usd": -2.0}
    send_report_notifications(AgentConfig(), report)

    assert len(photo_calls) == 1
    assert photo_calls[0]["caption"] == "דוח יומי 2026-07-22"
    assert photo_calls[0]["context"] == "report"
    assert photo_calls[0]["img"] == b"\x89PNG\r\n\x1a\nREPORT"
    assert photo_calls[0]["inbox_text"] == "דוח 2026-07-22"
    # Single Hebrew HTML card — no second English report:table photo
    assert english_table_calls == []
    assert all(c.get("context") != "report:table" for c in photo_calls)


def test_send_report_notifications_falls_back_to_html(monkeypatch):
    from trading_pulse.agent.dryrun_agent import AgentConfig, send_report_notifications

    notify_calls: list[dict] = []

    def _boom(_report):
        raise RuntimeError("pillow boom")

    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_daily_report",
        _boom,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_user_notification",
        lambda _cfg, text, **kw: notify_calls.append({"text": text, **kw}) or True,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.format_report_message",
        lambda _report: "<b>דוח HTML</b>",
    )

    send_report_notifications(AgentConfig(), {"trading_day": "2026-07-22"})

    assert len(notify_calls) == 1
    assert notify_calls[0]["context"] == "report"
    assert notify_calls[0]["parse_mode"] == "HTML"
    assert notify_calls[0]["text"] == "<b>דוח HTML</b>"


def test_send_entry_notifications_sends_card_photo(monkeypatch):
    from trading_pulse.agent.dryrun_agent import AgentConfig, send_entry_notifications

    photo_calls: list[dict] = []
    notify_calls: list = []

    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_entry",
        lambda entries, **kw: b"\x89PNG\r\n\x1a\nENTRY",
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_telegram_photo",
        lambda _cfg, img, caption, **kw: photo_calls.append(
            {"img": img, "caption": caption, **kw}
        )
        or True,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_user_notification",
        lambda *_a, **_k: notify_calls.append(True) or True,
    )

    entries = [{"symbol": "MPC", "capital_usd": 296, "entry_price": 319.0}]
    send_entry_notifications(
        AgentConfig(),
        entries,
        trading_day="2026-07-22",
        subtitle="קניה בוקר",
        context="entry:immediate",
    )

    assert len(photo_calls) == 1
    assert photo_calls[0]["caption"] == "קניה בוקר"
    assert photo_calls[0]["context"] == "entry:immediate"
    assert photo_calls[0]["img"] == b"\x89PNG\r\n\x1a\nENTRY"
    assert "MPC" in (photo_calls[0].get("inbox_text") or "")
    assert notify_calls == []


def test_send_entry_notifications_pending_method2_extra_html(monkeypatch):
    from trading_pulse.agent.dryrun_agent import AgentConfig, send_entry_notifications

    photo_calls: list[dict] = []
    notify_calls: list[dict] = []

    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_entry",
        lambda *_a, **_k: b"\x89PNG\r\n\x1a\nENTRY",
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_telegram_photo",
        lambda _cfg, img, caption, **kw: photo_calls.append(
            {"caption": caption, **kw}
        )
        or True,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_user_notification",
        lambda _cfg, text, **kw: notify_calls.append({"text": text, **kw}) or True,
    )

    send_entry_notifications(
        AgentConfig(),
        [{"symbol": "VLO", "capital_usd": 100, "entry_price": 150.0}],
        trading_day="2026-07-22",
        pending_method2=["PATH", "U"],
        context="entry",
    )

    assert len(photo_calls) == 1
    assert len(notify_calls) == 1
    assert notify_calls[0]["context"] == "entry:method2_pending"
    assert notify_calls[0]["parse_mode"] == "HTML"
    assert "PATH" in notify_calls[0]["text"]
    assert "ממתין לפריצה" in notify_calls[0]["text"]


def test_send_entry_notifications_empty_is_noop(monkeypatch):
    from trading_pulse.agent.dryrun_agent import AgentConfig, send_entry_notifications

    calls: list = []
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_telegram_photo",
        lambda *_a, **_k: calls.append("photo") or True,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_user_notification",
        lambda *_a, **_k: calls.append("notify") or True,
    )

    send_entry_notifications(AgentConfig(), [], trading_day="2026-07-22")
    assert calls == []


def test_send_entry_notifications_falls_back_to_html(monkeypatch):
    from trading_pulse.agent.dryrun_agent import AgentConfig, send_entry_notifications

    notify_calls: list[dict] = []

    def _boom(*_a, **_k):
        raise RuntimeError("pillow boom")

    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_entry",
        _boom,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_user_notification",
        lambda _cfg, text, **kw: notify_calls.append({"text": text, **kw}) or True,
    )

    send_entry_notifications(
        AgentConfig(),
        [{"symbol": "ARWR", "capital_usd": 147, "entry_price": 89.25}],
        trading_day="2026-07-22",
        context="entry",
    )

    assert len(notify_calls) == 1
    assert notify_calls[0]["context"] == "entry"
    assert notify_calls[0]["parse_mode"] == "HTML"
    assert "ARWR" in notify_calls[0]["text"]


def test_send_weekly_watchlist_notification_sends_card_photo(monkeypatch):
    from trading_pulse.agent.dryrun_agent import (
        AgentConfig,
        send_weekly_watchlist_notification,
    )

    photo_calls: list[dict] = []
    notify_calls: list = []
    result = {
        "week": "2026-W30",
        "scanned": 120,
        "universe_size": 420,
        "selected": 60,
        "symbols": ["AAA", "BBB"],
        "strategies_used": ["method2"],
        "strategy_hit_symbols": 5,
    }

    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_weekly_watchlist",
        lambda _result: b"\x89PNG\r\n\x1a\nWEEKLY",
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_telegram_photo",
        lambda _cfg, img, caption, **kw: photo_calls.append(
            {"img": img, "caption": caption, **kw}
        )
        or True,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_user_notification",
        lambda *_a, **_k: notify_calls.append(True) or True,
    )

    ok = send_weekly_watchlist_notification(AgentConfig(), result)

    assert ok is True
    assert len(photo_calls) == 1
    assert photo_calls[0]["caption"] == "רשימת מסחר 2026-W30"
    assert photo_calls[0]["context"] == "weekly_watchlist"
    assert photo_calls[0]["img"] == b"\x89PNG\r\n\x1a\nWEEKLY"
    inbox = photo_calls[0].get("inbox_text") or ""
    assert "נסרקו בהצלחה" in inbox
    assert "AAA" in inbox
    assert "<" not in inbox  # HTML stripped for app inbox
    assert notify_calls == []


def test_send_weekly_watchlist_notification_falls_back_to_html(monkeypatch):
    from trading_pulse.agent.dryrun_agent import (
        AgentConfig,
        send_weekly_watchlist_notification,
    )

    notify_calls: list[dict] = []

    def _boom(_result):
        raise RuntimeError("pillow boom")

    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_weekly_watchlist",
        _boom,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_user_notification",
        lambda _cfg, text, **kw: notify_calls.append({"text": text, **kw}) or True,
    )

    ok = send_weekly_watchlist_notification(
        AgentConfig(),
        {
            "week": "2026-W30",
            "scanned": 50,
            "universe_size": 420,
            "selected": 10,
            "symbols": ["ZZZ"],
            "strategies_used": [],
        },
        context="weekly_watchlist:cli",
    )

    assert ok is True
    assert len(notify_calls) == 1
    assert notify_calls[0]["context"] == "weekly_watchlist:cli"
    assert notify_calls[0]["parse_mode"] == "HTML"
    assert "נסרקו בהצלחה" in notify_calls[0]["text"]
    assert "ZZZ" in notify_calls[0]["text"]


def test_send_weekly_watchlist_notification_empty_week_caption(monkeypatch):
    from trading_pulse.agent.dryrun_agent import (
        AgentConfig,
        send_weekly_watchlist_notification,
    )

    photo_calls: list[dict] = []

    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.card_weekly_watchlist",
        lambda _result: b"\x89PNG\r\n\x1a\nWEEKLY",
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_telegram_photo",
        lambda _cfg, img, caption, **kw: photo_calls.append(
            {"caption": caption, **kw}
        )
        or True,
    )

    send_weekly_watchlist_notification(
        AgentConfig(),
        {"scanned": 1, "universe_size": 1, "selected": 1, "symbols": ["A"]},
    )

    assert photo_calls[0]["caption"] == "רשימת מסחר שבועית"


def _tiny_rgb_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    from io import BytesIO

    from PIL import Image

    im = Image.new("RGB", (width, height), color)
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_stack_png_vertical_combines_heights():
    from io import BytesIO

    from PIL import Image

    top = _tiny_rgb_png(80, 30, (10, 20, 30))
    bottom = _tiny_rgb_png(80, 20, (200, 100, 50))
    stacked = stack_png_vertical(top, bottom, gap=8)
    assert stacked.startswith(b"\x89PNG")
    w, h = Image.open(BytesIO(stacked)).size
    assert w == 80
    assert h == 30 + 8 + 20


def test_stack_png_vertical_scales_bottom_to_top_width():
    from io import BytesIO

    from PIL import Image

    top = _tiny_rgb_png(100, 40, (1, 2, 3))
    bottom = _tiny_rgb_png(50, 20, (9, 8, 7))
    stacked = stack_png_vertical(top, bottom, gap=4)
    w, h = Image.open(BytesIO(stacked)).size
    assert w == 100
    # bottom scaled 50→100 → height 20→40
    assert h == 40 + 4 + 40


def test_chart_with_recommendation_details_stacks(monkeypatch):
    from io import BytesIO

    from PIL import Image

    chart = _tiny_rgb_png(120, 50, (30, 30, 60))
    details = _tiny_rgb_png(120, 25, (60, 30, 30))
    monkeypatch.setattr(
        "trading_pulse.telegram.telegram_images.render_recommendation_chart",
        lambda *_a, **_k: chart,
    )
    monkeypatch.setattr(
        "trading_pulse.telegram.html_tables.card_png_from_html",
        lambda *_a, **_k: details,
    )
    out = chart_with_recommendation_details(
        {"symbol": "CLF", "capital_usd": 87, "entry_ref_price": 10.0,
         "stop_loss_pct": 0.12, "take_profit_pct": 0.25,
         "floor_price": 8.8, "take_profit_price": 12.5},
        1,
        "2026-07-27",
        signal_lines=["מומנטום"],
    )
    assert out is not None
    assert out.startswith(b"\x89PNG")
    w, h = Image.open(BytesIO(out)).size
    assert w == 120
    assert h == 50 + 8 + 25  # default gap=8


def test_chart_with_recommendation_details_returns_none_without_chart(monkeypatch):
    monkeypatch.setattr(
        "trading_pulse.telegram.telegram_images.render_recommendation_chart",
        lambda *_a, **_k: None,
    )
    assert (
        chart_with_recommendation_details({"symbol": "X"}, 1, "2026-07-27") is None
    )


def test_chart_with_recommendation_details_falls_back_to_chart(monkeypatch):
    chart = _tiny_rgb_png(60, 20, (11, 11, 11))
    monkeypatch.setattr(
        "trading_pulse.telegram.telegram_images.render_recommendation_chart",
        lambda *_a, **_k: chart,
    )
    monkeypatch.setattr(
        "trading_pulse.telegram.html_tables.card_png_from_html",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("html boom")),
    )
    out = chart_with_recommendation_details({"symbol": "CLF"}, 1, "2026-07-27")
    assert out == chart


def test_send_plan_stock_charts_short_caption(monkeypatch):
    from trading_pulse.agent.dryrun_agent import AgentConfig, send_plan_stock_charts

    photo_calls: list[dict] = []
    stacked = b"\x89PNG\r\n\x1a\nSTACKED"

    monkeypatch.setattr(
        "trading_pulse.telegram.app_notify.uses_telegram_notifications",
        lambda _cfg: True,
    )
    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.chart_with_recommendation_details",
        lambda *_a, **_k: stacked,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.send_telegram_photo",
        lambda _cfg, img, caption, **kw: photo_calls.append(
            {"img": img, "caption": caption, **kw}
        )
        or True,
    )

    send_plan_stock_charts(
        AgentConfig(notification_mode="telegram"),
        {
            "for_trading_day": "2026-07-27",
            "recommendations": [
                {
                    "symbol": "CLF",
                    "capital_usd": 87,
                    "entry_ref_price": 10.96,
                    "stop_loss_pct": 0.12,
                    "take_profit_pct": 0.25,
                    "floor_price": 9.64,
                    "take_profit_price": 13.70,
                    "score": 16.3,
                }
            ],
            "holdings": [],
        },
    )

    assert len(photo_calls) == 1
    assert photo_calls[0]["caption"] == "#1 CLF"
    assert photo_calls[0]["img"] == stacked
    assert photo_calls[0]["context"] == "plan:stock:CLF"
    assert photo_calls[0]["parse_mode"] == "HTML"
    assert "מחיר תחתון" not in photo_calls[0]["caption"]
    assert "יום מסחר 2026-07-27" in (photo_calls[0].get("inbox_text") or "")
