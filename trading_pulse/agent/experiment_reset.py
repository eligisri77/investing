"""Archive current dry-run state and start a clean experiment period."""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from trading_pulse.core.app_paths import CONFIG_FILE, DATA_DIR, INBOX_STATE_FILE, PLANS_DIR, REPORTS_DIR, STATE_FILE


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _archive_json_files(src: Path, dest: Path) -> list[str]:
    if not src.exists():
        return []
    dest.mkdir(parents=True, exist_ok=True)
    archived: list[str] = []
    for path in sorted(src.glob("*.json")):
        shutil.copy2(path, dest / path.name)
        archived.append(path.name)
    return archived


def _clear_json_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    removed = 0
    for path in directory.glob("*.json"):
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def reset_experiment(
    *,
    label: str,
    initial_capital: float | None = None,
    keep_history_in_archive: bool = True,
    month_key: str | None = None,
) -> dict[str, Any]:
    """
    Archive state + config snapshot, then reset equity/positions for a new experiment.
    Open positions are closed on paper (notional exit at entry) — fresh start.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_dir = DATA_DIR / "experiments" / f"{label}_{stamp}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    old_state = _read_json(STATE_FILE) if STATE_FILE.exists() else {}
    if keep_history_in_archive:
        _write_json(archive_dir / "state_before.json", old_state)
    if CONFIG_FILE.exists():
        shutil.copy2(CONFIG_FILE, archive_dir / "config_snapshot.json")

    archived_plans = _archive_json_files(PLANS_DIR, archive_dir / "plans")
    archived_reports = _archive_json_files(REPORTS_DIR, archive_dir / "reports")
    if INBOX_STATE_FILE.exists():
        shutil.copy2(INBOX_STATE_FILE, archive_dir / "inbox_state_before.json")

    capital = float(initial_capital) if initial_capital is not None else None
    if capital is None:
        capital = float(_read_json(CONFIG_FILE).get("initial_capital", 1000.0)) if CONFIG_FILE.exists() else 1000.0

    today = date.today()
    month_key = month_key or today.strftime("%Y-%m")
    month_start = date.fromisoformat(f"{month_key}-01")
    new_state: dict[str, Any] = {
        "equity": round(capital, 2),
        "last_report_date": None,
        "history": [],
        "open_positions": [],
        "symbol_cooldowns": {},
        "intraday_floor_exits": [],
        "intraday_alert_cooldowns": {},
        "month_key": month_key,
        "month_start_equity": round(capital, 2),
        "month_start_date": month_start.isoformat(),
        "experiment": {
            "label": label,
            "month_key": month_key,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "archived_from": str(archive_dir),
            "starting_equity": round(capital, 2),
        },
    }
    if old_state.get("telegram_last_update_id") is not None:
        new_state["telegram_last_update_id"] = old_state["telegram_last_update_id"]
    if keep_history_in_archive and old_state.get("history"):
        new_state["experiment"]["prior_history_days"] = len(old_state["history"])
        new_state["experiment"]["prior_final_equity"] = old_state.get("equity")

    _write_json(STATE_FILE, new_state)
    _write_json(
        INBOX_STATE_FILE,
        {"unread": 0, "pending_plan_day": None, "last_notification_at": None},
    )
    cleared_plans = _clear_json_files(PLANS_DIR)
    cleared_reports = _clear_json_files(REPORTS_DIR)
    return {
        "ok": True,
        "label": label,
        "archive_dir": str(archive_dir),
        "starting_equity": capital,
        "month_key": month_key,
        "archived_plans": len(archived_plans),
        "archived_reports": len(archived_reports),
        "cleared_plans": cleared_plans,
        "cleared_reports": cleared_reports,
    }
