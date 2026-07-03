"""Prevent multiple Trading Pulse / scheduler instances."""

from __future__ import annotations

import atexit
import logging
import os
import sys
from pathlib import Path

from trading_pulse.core.app_paths import LOCK_FILE

_lock_held = False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_lock() -> tuple[int, str] | None:
    if not LOCK_FILE.exists():
        return None
    try:
        parts = LOCK_FILE.read_text(encoding="utf-8").strip().split()
        if len(parts) >= 1:
            return int(parts[0]), parts[1] if len(parts) > 1 else "unknown"
    except (ValueError, OSError):
        pass
    return None


def release_instance_lock() -> None:
    global _lock_held
    if not _lock_held:
        return
    try:
        current = _read_lock()
        if current and current[0] == os.getpid() and LOCK_FILE.exists():
            LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    _lock_held = False


def acquire_instance_lock(role: str = "app") -> bool:
    """Return True if this process owns the lock."""
    global _lock_held
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    existing = _read_lock()
    if existing:
        pid, existing_role = existing
        if pid == os.getpid():
            _lock_held = True
            return True
        if _pid_alive(pid):
            logging.error(
                "Another Trading Pulse instance is running (pid=%s, role=%s). Exiting.",
                pid,
                existing_role,
            )
            return False

    try:
        LOCK_FILE.write_text(f"{os.getpid()} {role}\n", encoding="utf-8")
    except OSError as ex:
        logging.error("Could not write instance lock: %s", ex)
        return False

    _lock_held = True
    atexit.register(release_instance_lock)
    return True


def lock_status() -> dict:
    existing = _read_lock()
    if not existing:
        return {"locked": False, "pid": None, "role": None, "alive": False}
    pid, role = existing
    alive = _pid_alive(pid)
    return {"locked": True, "pid": pid, "role": role, "alive": alive, "this_process": pid == os.getpid()}
