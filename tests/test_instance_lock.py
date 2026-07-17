"""Tests for single-instance lock, incl. stale-lock reclaim after unclean shutdown."""

from __future__ import annotations

import os

import trading_pulse.core.instance_lock as il


def _use_temp_lock(tmp_path, monkeypatch):
    lock = tmp_path / "trading_pulse.lock"
    monkeypatch.setattr(il, "LOCK_FILE", lock)
    monkeypatch.setattr(il, "_lock_held", False)
    monkeypatch.setattr(il, "_win_mutex", None)
    monkeypatch.setattr(il, "_acquire_windows_mutex", lambda: True)
    return lock


def test_acquire_when_no_lock(tmp_path, monkeypatch):
    _use_temp_lock(tmp_path, monkeypatch)
    assert il.acquire_instance_lock("app") is True


def test_reclaims_stale_lock_from_dead_pid(tmp_path, monkeypatch):
    lock = _use_temp_lock(tmp_path, monkeypatch)
    lock.write_text("999999 app\n", encoding="utf-8")  # implausible/dead pid
    monkeypatch.setattr(il, "_is_our_process", lambda pid: False)
    assert il.acquire_instance_lock("app") is True
    assert str(os.getpid()) in lock.read_text(encoding="utf-8")


def test_reclaims_lock_when_pid_reused_by_other_process(tmp_path, monkeypatch):
    lock = _use_temp_lock(tmp_path, monkeypatch)
    lock.write_text("4321 app\n", encoding="utf-8")
    # PID alive but NOT a python process (reused after reboot)
    monkeypatch.setattr(il, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(il, "_process_image_name", lambda pid: r"C:\Windows\explorer.exe")
    assert il.acquire_instance_lock("app") is True


def test_refuses_when_our_process_alive(tmp_path, monkeypatch):
    lock = _use_temp_lock(tmp_path, monkeypatch)
    lock.write_text("4321 app\n", encoding="utf-8")
    monkeypatch.setattr(il, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(il, "_process_image_name", lambda pid: r"D:\venv\Scripts\pythonw.exe")
    assert il.acquire_instance_lock("app") is False


def test_refuses_when_installed_exe_alive(tmp_path, monkeypatch):
    """Installed build runs TradingPulse.exe — must count as our process."""
    lock = _use_temp_lock(tmp_path, monkeypatch)
    lock.write_text("4321 app\n", encoding="utf-8")
    monkeypatch.setattr(il, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(
        il,
        "_process_image_name",
        lambda pid: r"C:\Users\Eli\AppData\Local\Programs\TradingPulse\TradingPulse.exe",
    )
    assert il.acquire_instance_lock("app") is False


def test_second_acquire_in_same_process_is_idempotent(tmp_path, monkeypatch):
    _use_temp_lock(tmp_path, monkeypatch)
    assert il.acquire_instance_lock("app") is True
    assert il.acquire_instance_lock("app") is True
