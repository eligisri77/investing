"""Scheduler job health metadata for dashboard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_pulse.core.instance_lock import lock_status

from trading_pulse.core.app_paths import HEALTH_FILE, PLANS_DIR, REPORTS_DIR, SCHEDULER_LOG_FILE


def _ensure() -> None:
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_health() -> dict[str, Any]:
    _ensure()
    if not HEALTH_FILE.exists():
        return {"jobs": {}, "last_error": None}
    with HEALTH_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_health(data: dict[str, Any]) -> None:
    _ensure()
    with HEALTH_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def record_job(name: str, status: str, detail: str = "", **extra: Any) -> None:
    data = load_health()
    now = datetime.now(timezone.utc).isoformat()
    jobs = data.setdefault("jobs", {})
    jobs[name] = {
        "status": status,
        "at": now,
        "detail": detail,
        **extra,
    }
    if status == "failed":
        data["last_error"] = {"job": name, "at": now, "detail": detail}
    elif status == "ok":
        last_error = data.get("last_error")
        if isinstance(last_error, dict) and last_error.get("job") == name:
            data["last_error"] = None
    save_health(data)


def tail_log(lines: int = 8) -> list[str]:
    if not SCHEDULER_LOG_FILE.exists():
        return []
    try:
        content = SCHEDULER_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        return content[-lines:]
    except OSError:
        return []


def collect_health(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    data = load_health()
    jobs = data.get("jobs", {})
    plans_dir = PLANS_DIR
    reports_dir = REPORTS_DIR

    latest_plan = None
    latest_plan_mtime = None
    if plans_dir.exists():
        plan_files = sorted(plans_dir.glob("plan_*.json"), reverse=True)
        if plan_files:
            latest_plan = plan_files[0].stem.replace("plan_", "")
            latest_plan_mtime = datetime.fromtimestamp(
                plan_files[0].stat().st_mtime, tz=timezone.utc
            ).isoformat()

    latest_report = None
    if reports_dir.exists():
        report_files = sorted(reports_dir.glob("report_*.json"), reverse=True)
        if report_files:
            latest_report = report_files[0].stem.replace("report_", "")

    lock = lock_status()
    scheduler_ok = lock.get("alive") and lock.get("locked")

    return {
        "status": "ok" if scheduler_ok else "offline",
        "instance": lock,
        "notification_mode": (cfg or {}).get("notification_mode", "app"),
        "secrets_source": _secrets_source_safe(),
        "schedule": {
            "planning_time": (cfg or {}).get("planning_time"),
            "market_open_sim_time": (cfg or {}).get("market_open_sim_time"),
            "market_close_sim_time": (cfg or {}).get("market_close_sim_time"),
            "heartbeat_time": (cfg or {}).get("heartbeat_time"),
            "intraday_check_enabled": (cfg or {}).get("intraday_check_enabled"),
            "intraday_check_interval_minutes": (cfg or {}).get("intraday_check_interval_minutes"),
            "intraday_alert_cooldown_minutes": (cfg or {}).get("intraday_alert_cooldown_minutes"),
            "telegram_poll_interval_sec": (cfg or {}).get("telegram_poll_interval_sec"),
        },
        "jobs": jobs,
        "last_error": data.get("last_error"),
        "latest_plan_day": latest_plan,
        "latest_plan_at": latest_plan_mtime,
        "latest_report_day": latest_report,
        "log_tail": tail_log(6),
    }


def _secrets_source_safe() -> str:
    try:
        from trading_pulse.core.env_config import secrets_source

        return secrets_source()
    except ImportError:
        return "unknown"
