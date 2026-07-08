"""Prevent multiple Trading Pulse / scheduler instances."""

from __future__ import annotations

import atexit
import logging
import os
import sys
from pathlib import Path

from trading_pulse.core.app_paths import LOCK_FILE

_lock_held = False


def _process_image_name(pid: int) -> str | None:
    """Best-effort executable name for a live PID (Windows)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        buf_len = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(buf_len.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(buf_len)):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(handle)


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


def _is_our_process(pid: int) -> bool:
    """True only if the live PID is actually a python process (not a reused PID).

    Guards against PID reuse after an unclean shutdown (e.g. power loss), where a
    stale lock's PID may have been reassigned to an unrelated process at boot.
    """
    if not _pid_alive(pid):
        return False
    image = _process_image_name(pid)
    if image is None:
        # Can't verify (non-Windows or query failed) — fall back to alive check.
        return sys.platform != "win32"
    name = os.path.basename(image).lower()
    return name in {"python.exe", "pythonw.exe"}


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
        if _is_our_process(pid):
            logging.error(
                "Another Trading Pulse instance is running (pid=%s, role=%s). Exiting.",
                pid,
                existing_role,
            )
            return False
        logging.warning(
            "Found stale lock (pid=%s, role=%s) — previous instance gone. Reclaiming.",
            pid,
            existing_role,
        )

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
    alive = _is_our_process(pid)
    return {"locked": True, "pid": pid, "role": role, "alive": alive, "this_process": pid == os.getpid()}
