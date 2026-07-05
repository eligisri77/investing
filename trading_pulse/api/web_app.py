"""Local web dashboard for dry-run trading recommendations."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import uvicorn
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from trading_pulse.telegram.telegram_store import load_messages, merge_backfill

from trading_pulse.core.app_settings import get_settings_payload, update_settings
from trading_pulse.telegram.telegram_settings import get_telegram_settings_payload, test_telegram_connection, update_telegram_settings
from trading_pulse.telegram.app_notify import inbox_summary, mark_inbox_read
from trading_pulse.guides.selection_guide import get_selection_guide
from trading_pulse.telegram.telegram_guide import get_telegram_guide
from trading_pulse.telegram.telegram_bot_guide import get_telegram_bot_guide
from trading_pulse.agent.health_tracker import collect_health
from trading_pulse.agent.portfolio import build_portfolio

try:
    from trading_pulse.agent.dryrun_agent import (
        apply_allocation_choice,
        format_heartbeat_message,
        format_plan_message,
        format_report_message,
        generate_plan,
        get_active_trading_day,
        load_config as load_agent_config,
        load_state as load_agent_state,
        parse_indices,
        plan_path,
        send_plan_notifications,
        set_plan_status,
        start_investing,
    )
    from trading_pulse.agent.capital_allocation import allocation_options_payload, allocation_pending
    from trading_pulse.agent.signal_sources import SOURCE_LABELS
except ImportError:
    format_plan_message = None  # type: ignore
    SOURCE_LABELS = {}  # type: ignore
    generate_plan = None  # type: ignore
    send_plan_notifications = None  # type: ignore
    start_investing = None  # type: ignore
    get_active_trading_day = None  # type: ignore
    apply_allocation_choice = None  # type: ignore
    allocation_options_payload = None  # type: ignore
    allocation_pending = None  # type: ignore
    load_agent_state = None  # type: ignore

from trading_pulse.core.app_paths import (
    CONFIG_FILE,
    DATA_DIR,
    PLANS_DIR,
    REPORTS_DIR,
    STATE_FILE,
    WEB_STATIC_DIR,
)

app = FastAPI(title="Dry Run Trading Dashboard", version="1.0.0")


class PlanActionRequest(BaseModel):
    action: str = Field(description="approve or reject")
    indices: list[int] | str = Field(default="ALL", description="1-based indices or ALL")


class PlanAllocationRequest(BaseModel):
    option_id: int = Field(ge=1, le=5, description="Allocation option 1-5 (ח1…ח5)")


class SettingsUpdateRequest(BaseModel):
    values: dict[str, Any] = Field(description="Editable config keys to update")


class TelegramSettingsUpdate(BaseModel):
    bot_token: str = Field(default="", description="Bot token from @BotFather; empty keeps current")
    chat_id: str = Field(default="", description="Numeric chat id; empty keeps current")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"equity": 1000.0, "history": []}
    return read_json(STATE_FILE)


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    return read_json(CONFIG_FILE)


def load_report(trading_day: str) -> dict[str, Any] | None:
    path = REPORTS_DIR / f"report_{trading_day}.json"
    if not path.exists():
        return None
    return read_json(path)


def load_plan(trading_day: str) -> dict[str, Any] | None:
    path = PLANS_DIR / f"plan_{trading_day}.json"
    if not path.exists():
        return None
    return read_json(path)


def extract_series(df: pd.DataFrame, col: str) -> pd.Series:
    series = df[col]
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    return series


def hypothetical_trade(rec: dict[str, Any], trading_day: str) -> dict[str, Any] | None:
    symbol = rec["symbol"]
    day_df = yf.download(
        symbol,
        start=trading_day,
        end=(date.fromisoformat(trading_day) + timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    ).dropna()
    if day_df.empty:
        return None

    o = float(extract_series(day_df, "Open").iloc[0])
    h = float(extract_series(day_df, "High").iloc[0])
    l = float(extract_series(day_df, "Low").iloc[0])
    c = float(extract_series(day_df, "Close").iloc[0])
    stop_pct = float(rec.get("stop_loss_pct", 0.12))
    take_pct = float(rec.get("take_profit_pct", 0.25))
    stop_price = o * (1 - stop_pct)
    take_price = o * (1 + take_pct)

    if l <= stop_price:
        exit_price, exit_reason = stop_price, "stop_loss"
    elif h >= take_price:
        exit_price, exit_reason = take_price, "take_profit"
    else:
        exit_price, exit_reason = c, "close"

    capital = float(rec.get("capital_usd", 0))
    pnl_pct = (exit_price / o) - 1
    return {
        "entry_price": round(o, 4),
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "capital_usd": round(capital, 2),
        "pnl_pct": round(pnl_pct * 100, 3),
        "pnl_usd": round(capital * pnl_pct, 2),
        "hypothetical": True,
    }


def build_source_breakdown(rec: dict[str, Any]) -> list[dict[str, Any]]:
    source_scores = rec.get("source_scores") or {}
    if not source_scores:
        return []
    return [
        {
            "id": source_id,
            "label": SOURCE_LABELS.get(source_id, source_id),
            "score": round(float(score), 2),
        }
        for source_id, score in sorted(source_scores.items(), key=lambda x: -float(x[1]))
    ]


def build_pick_record(plan: dict[str, Any], rec: dict[str, Any]) -> dict[str, Any]:
    trading_day = plan["for_trading_day"]
    report = load_report(trading_day)
    executed = None
    if report and rec.get("approved"):
        for trade in report.get("executed", []):
            if trade.get("symbol") == rec["symbol"]:
                executed = trade
                break

    skipped_hypo = None
    if not executed:
        try:
            skipped_hypo = hypothetical_trade(rec, trading_day)
        except Exception:
            skipped_hypo = None

    return {
        "symbol": rec["symbol"],
        "trading_day": trading_day,
        "generated_at": plan.get("generated_at"),
        "approved": bool(rec.get("approved")),
        "invested": executed is not None,
        "side": rec.get("side", "LONG"),
        "capital_usd": float(rec.get("capital_usd", 0)),
        "entry_ref_price": float(rec.get("entry_ref_price", 0)),
        "stop_loss_pct": float(rec.get("stop_loss_pct", 0)),
        "take_profit_pct": float(rec.get("take_profit_pct", 0)),
        "floor_price": float(rec.get("floor_price") or rec.get("stop_loss_price") or 0) or None,
        "score": float(rec.get("score", 0)),
        "score_technical": rec.get("score_technical"),
        "score_simple_avg": rec.get("score_simple_avg"),
        "source_score_std": rec.get("source_score_std"),
        "source_score_spread": rec.get("source_score_spread"),
        "source_disagreement": bool(rec.get("source_disagreement", False)),
        "sentiment_tone": rec.get("sentiment_tone"),
        "sentiment_adjustment": rec.get("sentiment_adjustment"),
        "score_before_sentiment": rec.get("score_before_sentiment"),
        "backtest": rec.get("backtest"),
        "ret_5d_pct": float(rec.get("ret_5d_pct", 0)),
        "vol_ratio": rec.get("vol_ratio"),
        "atr_pct": rec.get("atr_pct"),
        "near_high_pct": rec.get("near_high_pct"),
        "breakout_ok": rec.get("breakout_ok"),
        "volume_ok": rec.get("volume_ok"),
        "source_scores": rec.get("source_scores") or {},
        "sources_used": int(rec.get("sources_used") or 0),
        "source_breakdown": build_source_breakdown(rec),
        "news_summary": rec.get("news_summary", ""),
        "news_headlines": rec.get("news_headlines", []),
        "trade": executed,
        "hypothetical_if_skipped": skipped_hypo,
    }


def load_all_picks(limit: int = 60) -> list[dict[str, Any]]:
    picks: list[dict[str, Any]] = []
    plan_files = sorted(PLANS_DIR.glob("plan_*.json"), reverse=True)
    for path in plan_files[:limit]:
        plan = read_json(path)
        for rec in plan.get("recommendations", []):
            picks.append(build_pick_record(plan, rec))
    picks.sort(key=lambda x: (x["trading_day"], x["symbol"]), reverse=True)
    return picks


def fetch_price_history(symbol: str, trading_day: str, window_days: int = 7) -> list[dict[str, Any]]:
    center = date.fromisoformat(trading_day)
    start = center - timedelta(days=window_days)
    end = center + timedelta(days=window_days)
    df = yf.download(
        symbol,
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    ).dropna()
    if df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        day_str = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
        rows.append(
            {
                "date": day_str,
                "open": round(float(extract_series(df.loc[[idx]], "Open").iloc[0]), 4),
                "high": round(float(extract_series(df.loc[[idx]], "High").iloc[0]), 4),
                "low": round(float(extract_series(df.loc[[idx]], "Low").iloc[0]), 4),
                "close": round(float(extract_series(df.loc[[idx]], "Close").iloc[0]), 4),
                "highlight": day_str == trading_day,
            }
        )
    return rows


@app.get("/api/selection/guide")
def api_selection_guide() -> dict[str, Any]:
    return get_selection_guide(load_config())


@app.get("/api/telegram/guide")
def api_telegram_guide() -> dict[str, Any]:
    return get_telegram_guide(load_config())


@app.get("/api/telegram/bot-guide")
def api_telegram_bot_guide() -> dict[str, Any]:
    return get_telegram_bot_guide()


@app.get("/api/settings")
def api_settings_get() -> dict[str, Any]:
    return get_settings_payload()


@app.put("/api/settings")
def api_settings_put(body: SettingsUpdateRequest) -> dict[str, Any]:
    return update_settings(body.values)


@app.get("/api/settings/telegram")
def api_telegram_settings_get() -> dict[str, Any]:
    return get_telegram_settings_payload()


@app.put("/api/settings/telegram")
def api_telegram_settings_put(body: TelegramSettingsUpdate) -> dict[str, Any]:
    payload = update_telegram_settings(bot_token=body.bot_token, chat_id=body.chat_id)
    return {"ok": True, **payload}


@app.post("/api/settings/telegram/test")
def api_telegram_settings_test(body: TelegramSettingsUpdate) -> dict[str, Any]:
    return test_telegram_connection(bot_token=body.bot_token, chat_id=body.chat_id)


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    cfg = load_config()
    return collect_health(cfg)


@app.get("/api/dashboard")
def api_dashboard() -> dict[str, Any]:
    state = load_state()
    cfg = load_config()
    picks = load_all_picks()
    symbols = sorted({p["symbol"] for p in picks}, key=lambda s: s)
    invested = [p for p in picks if p["invested"]]
    total_pnl = sum(float(p["trade"]["pnl_usd"]) for p in invested if p.get("trade"))
    return {
        "equity": float(state.get("equity", cfg.get("initial_capital", 1000))),
        "monthly_target_usd": float(cfg.get("monthly_target_usd", 2000)),
        "month_start_equity": float(state.get("month_start_equity", 1000)),
        "risk_profile": cfg.get("risk_profile", "speculative"),
        "notification_mode": cfg.get("notification_mode", "app"),
        "inbox": inbox_summary(),
        "total_picks": len(picks),
        "invested_count": len(invested),
        "total_realized_pnl": round(total_pnl, 2),
        "symbols": symbols,
        "recent_picks": picks[:12],
        "equity_history": [
            {
                "day": h.get("trading_day"),
                "equity": h.get("equity_after"),
                "pnl": h.get("pnl_usd"),
            }
            for h in state.get("history", [])
        ],
    }


@app.get("/api/portfolio")
def api_portfolio() -> dict[str, Any]:
    return build_portfolio()


@app.get("/api/picks")
def api_picks() -> list[dict[str, Any]]:
    return load_all_picks()


@app.get("/api/stock/{symbol}")
def api_stock(symbol: str) -> dict[str, Any]:
    symbol = symbol.upper()
    picks = [p for p in load_all_picks() if p["symbol"] == symbol]
    if not picks:
        raise HTTPException(status_code=404, detail=f"No recommendations for {symbol}")

    invested_pnl = sum(
        float(p["trade"]["pnl_usd"]) for p in picks if p.get("trade")
    )
    skipped_hypo_pnl = sum(
        float(p["hypothetical_if_skipped"]["pnl_usd"])
        for p in picks
        if p.get("hypothetical_if_skipped")
    )

    return {
        "symbol": symbol,
        "picks": picks,
        "stats": {
            "total_recommendations": len(picks),
            "invested_count": sum(1 for p in picks if p["invested"]),
            "skipped_count": sum(1 for p in picks if not p["approved"]),
            "realized_pnl_usd": round(invested_pnl, 2),
            "skipped_hypothetical_pnl_usd": round(skipped_hypo_pnl, 2),
        },
    }


@app.get("/api/stock/{symbol}/chart")
def api_stock_chart(symbol: str, day: str, window: int = 7) -> dict[str, Any]:
    symbol = symbol.upper()
    try:
        date.fromisoformat(day)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail="Invalid date") from ex
    prices = fetch_price_history(symbol, day, window_days=window)
    if not prices:
        raise HTTPException(status_code=404, detail="No price data")
    return {"symbol": symbol, "trading_day": day, "prices": prices}


def backfill_telegram_messages() -> int:
    if format_plan_message is None:
        return 0
    entries: list[dict[str, Any]] = []

    for path in sorted(PLANS_DIR.glob("plan_*.json")):
        plan = read_json(path)
        day = plan.get("for_trading_day", path.stem.replace("plan_", ""))
        entries.append(
            {
                "id": f"out:plan:{day}",
                "direction": "out",
                "context": "plan",
                "text": format_plan_message(plan),
                "parse_mode": "HTML",
                "timestamp": plan.get("generated_at") or f"{day}T21:00:00+00:00",
                "backfilled": True,
                "metadata": {"trading_day": day},
            }
        )

    for path in sorted(REPORTS_DIR.glob("report_*.json")):
        report = read_json(path)
        day = report.get("trading_day", path.stem.replace("report_", ""))
        entries.append(
            {
                "id": f"out:report:{day}",
                "direction": "out",
                "context": "report",
                "text": format_report_message(report),
                "parse_mode": "HTML",
                "timestamp": f"{day}T23:10:00+00:00",
                "backfilled": True,
                "metadata": {"trading_day": day},
            }
        )

    state = load_state()
    if state.get("last_heartbeat_at"):
        try:
            cfg = load_agent_config()
            hb_text = format_heartbeat_message(cfg, state)
            entries.append(
                {
                    "id": f"out:heartbeat:{state['last_heartbeat_at'][:10]}",
                    "direction": "out",
                    "context": "heartbeat",
                    "text": hb_text,
                    "parse_mode": "HTML",
                    "timestamp": state["last_heartbeat_at"],
                    "backfilled": True,
                    "metadata": {},
                }
            )
        except Exception:
            pass

    return merge_backfill(entries)


@app.get("/api/inbox/summary")
def api_inbox_summary() -> dict[str, Any]:
    return inbox_summary()


@app.post("/api/inbox/read")
def api_inbox_mark_read() -> dict[str, bool]:
    mark_inbox_read()
    return {"ok": True}


@app.post("/api/plan/start")
def api_plan_start() -> dict[str, Any]:
    if start_investing is None:
        raise HTTPException(status_code=503, detail="Agent module unavailable")
    return start_investing(load_agent_config())


@app.post("/api/plan/generate-now")
def api_plan_generate_now() -> dict[str, Any]:
    if generate_plan is None or send_plan_notifications is None or load_agent_config is None:
        raise HTTPException(status_code=503, detail="Agent module unavailable")
    cfg = load_agent_config()
    state = load_agent_state(cfg)
    plan = generate_plan(cfg, state, date.today(), force=True)
    send_plan_notifications(cfg, plan)
    trading_day = str(plan.get("for_trading_day", ""))
    return {
        "ok": True,
        "trading_day": trading_day,
        "recommendations": len(plan.get("recommendations", [])),
    }


@app.get("/api/plan/active")
def api_plan_active() -> dict[str, Any]:
    if get_active_trading_day is None:
        raise HTTPException(status_code=503, detail="Agent module unavailable")
    trading_day = get_active_trading_day()
    if not trading_day:
        raise HTTPException(status_code=404, detail="No active plan")
    path = plan_path(date.fromisoformat(trading_day))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Plan file missing")
    plan = read_json(path)
    recs = plan.get("recommendations", [])
    pending = any(not r.get("approved") for r in recs) if recs else False
    alloc = plan.get("allocation") or {}
    allocation_options = None
    alloc_pending = False
    bought = False
    entry_when = None
    if allocation_pending is not None and allocation_options_payload is not None and load_agent_state is not None:
        alloc_pending = allocation_pending(plan)
        if alloc_pending:
            cfg_agent = load_agent_config()
            state = load_agent_state(cfg_agent)
            allocation_options = allocation_options_payload(cfg_agent, plan, state)
    try:
        from trading_pulse.agent.trading_flow import entries_already_run, scheduled_entry_moment

        td = date.fromisoformat(trading_day)
        bought = entries_already_run(plan, td)
        entry_when = scheduled_entry_moment(load_agent_config(), td)
    except Exception:
        bought = False
        entry_when = None
    return {
        "trading_day": trading_day,
        "pending": pending,
        "allocation_pending": alloc_pending,
        "allocation_applied": alloc.get("status") == "applied",
        "allocation": alloc if alloc else None,
        "allocation_options": allocation_options,
        "plan": plan,
        "ready": bool(recs) and not pending and alloc.get("status") == "applied",
        "bought": bought,
        "entry_when": entry_when,
    }


@app.post("/api/plan/{trading_day}/action")
def api_plan_action(trading_day: str, body: PlanActionRequest) -> dict[str, Any]:
    if set_plan_status is None or parse_indices is None:
        raise HTTPException(status_code=503, detail="Agent module unavailable")
    try:
        date.fromisoformat(trading_day)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail="Invalid date") from ex

    path = plan_path(date.fromisoformat(trading_day))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = read_json(path)
    total = len(plan.get("recommendations", []))
    if isinstance(body.indices, list):
        indices = sorted({int(i) - 1 for i in body.indices if 0 < int(i) <= total})
    else:
        indices = parse_indices(str(body.indices).upper(), total=total)
    if not indices:
        raise HTTPException(status_code=400, detail="No valid indices")

    action = body.action.upper()
    if action not in {"APPROVE", "REJECT"}:
        raise HTTPException(status_code=400, detail="action must be approve or reject")

    message = set_plan_status(trading_day, action, indices)
    updated = read_json(path)
    return {
        "ok": True,
        "message": message,
        "plan": updated,
        "inbox": inbox_summary(),
    }


@app.post("/api/plan/{trading_day}/allocation")
def api_plan_allocation(trading_day: str, body: PlanAllocationRequest) -> dict[str, Any]:
    if apply_allocation_choice is None:
        raise HTTPException(status_code=503, detail="Agent module unavailable")
    try:
        date.fromisoformat(trading_day)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail="Invalid date") from ex

    path = plan_path(date.fromisoformat(trading_day))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Plan not found")

    if allocation_pending is not None:
        plan = read_json(path)
        if not allocation_pending(plan):
            raise HTTPException(status_code=400, detail="Allocation not pending for this plan")

    cfg = load_agent_config()
    message = apply_allocation_choice(trading_day, body.option_id, cfg=cfg)
    from trading_pulse.telegram.telegram_store import append_message as log_telegram_message

    log_telegram_message(
        "in",
        "app:allocation",
        f"ח{body.option_id} ({trading_day})",
        metadata={"trading_day": trading_day, "option_id": body.option_id},
    )
    updated = read_json(path)
    alloc_pending = allocation_pending(updated) if allocation_pending else False
    return {
        "ok": True,
        "message": message,
        "plan": updated,
        "allocation_pending": alloc_pending,
        "inbox": inbox_summary(),
    }


@app.get("/api/telegram/messages")
def api_telegram_messages() -> dict[str, Any]:
    backfill_telegram_messages()
    messages = load_messages()
    messages.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    return {
        "total": len(messages),
        "messages": messages,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_STATIC_DIR), name="static")


APP_HOST = "127.0.0.1"
APP_PORT = 8765


def run_web_server(host: str = APP_HOST, port: int = APP_PORT) -> None:
    WEB_STATIC_DIR.mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> None:
    print(f"Dashboard: http://{APP_HOST}:{APP_PORT}")
    run_web_server()


if __name__ == "__main__":
    main()
