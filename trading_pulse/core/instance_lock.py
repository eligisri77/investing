"""Prevent multiple Trading Pulse / scheduler instances."""

from __future__ import annotations

import atexit
import logging
import os
import sys
import time
from pathlib import Path

from trading_pulse.core.app_paths import LOCK_FILE

_lock_held = False
_win_mutex = None


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
    return name in {"python.exe", "pythonw.exe", "tradingpulse.exe"}


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


def _acquire_windows_mutex() -> bool:
    """Atomic single-instance guard (Windows). Returns False if another instance holds it."""
    global _win_mutex
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.windll.kernel32
    ERROR_ALREADY_EXISTS = 183
    handle = kernel32.CreateMutexW(None, False, "Local\\TradingPulse.SingleInstance")
    if not handle:
        logging.error("Could not create single-instance mutex")
        return False
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _win_mutex = handle
    return True


def _release_windows_mutex() -> None:
    global _win_mutex
    if _win_mutex is None:
        return
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.CloseHandle(_win_mutex)
    _win_mutex = None


def _try_claim_lock_file(role: str) -> bool:
    """Atomically create the lock file (O_EXCL). Returns False if another live instance owns it."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = f"{os.getpid()} {role}\n".encode("utf-8")
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        existing = _read_lock()
        if not existing:
            return False
        pid, existing_role = existing
        if pid == os.getpid():
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
            LOCK_FILE.unlink(missing_ok=True)
        except OSError:
            return False
        return False
    except OSError as ex:
        logging.error("Could not create instance lock: %s", ex)
        return False

    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    return True


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
    _release_windows_mutex()
    _lock_held = False


def acquire_instance_lock(role: str = "app") -> bool:
    """Return True if this process owns the lock."""
    global _lock_held
    if _lock_held:
        return True

    if not _acquire_windows_mutex():
        logging.error("Another Trading Pulse instance is already running (mutex). Exiting.")
        return False

    for attempt in range(3):
        if _try_claim_lock_file(role):
            _lock_held = True
            atexit.register(release_instance_lock)
            return True
        if attempt < 2:
            time.sleep(0.05)

    _release_windows_mutex()
    logging.error("Could not acquire instance lock after retries.")
    return False


def lock_status() -> dict:
    existing = _read_lock()
    if not existing:
        return {"locked": False, "pid": None, "role": None, "alive": False}
    pid, role = existing
    alive = _is_our_process(pid)
    return {"locked": True, "pid": pid, "role": role, "alive": alive, "this_process": pid == os.getpid()}
