"""Windows desktop app: system tray + embedded dashboard + background scheduler."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pystray
import webview
from PIL import Image, ImageDraw

from trading_pulse.core.bootstrap import ensure_first_run

ensure_first_run()

from trading_pulse.agent.dryrun_agent import (
    ensure_dirs,
    generate_plan,
    load_config,
    load_state,
    plan_path,
    run_scheduler_loop,
    scheduler_log_file,
    send_heartbeat,
    send_plan_notifications,
    setup_logger,
)
from trading_pulse.core.instance_lock import acquire_instance_lock
from trading_pulse.api.web_app import APP_HOST, APP_PORT, run_web_server

DASHBOARD_URL = f"http://{APP_HOST}:{APP_PORT}/"
APP_TITLE = "Trading Pulse"


class TradingPulseApp:
    def __init__(self, *, start_hidden: bool = False) -> None:
        self.window: webview.Window | None = None
        self.tray: pystray.Icon | None = None
        self._started = False
        self._lock = threading.Lock()
        self._start_hidden = start_hidden

        self._last_inbox_unread = 0

    def dashboard_url(self) -> str:
        return DASHBOARD_URL

    def _run_scheduler_safe(self) -> None:
        """Keep the scheduler alive — a single crash must not kill EOD / Telegram forever."""
        backoff_sec = 5.0
        while True:
            try:
                run_scheduler_loop(service=True)
                logging.warning("Scheduler loop exited; restarting in %.0fs", backoff_sec)
            except Exception:
                logging.exception("Scheduler thread crashed; restarting in %.0fs", backoff_sec)
            time.sleep(backoff_sec)
            backoff_sec = min(60.0, backoff_sec * 1.5)

    def start_background_services(self) -> None:
        with self._lock:
            if self._started:
                return
            ensure_dirs()
            setup_logger(scheduler_log_file())
            cfg = load_config()
            logging.info(
                "Trading Pulse app starting background services (notification_mode=%s)",
                cfg.notification_mode,
            )

            threading.Thread(
                target=run_web_server,
                kwargs={"host": APP_HOST, "port": APP_PORT},
                name="web-server",
                daemon=True,
            ).start()
            threading.Thread(
                target=self._run_scheduler_safe,
                name="scheduler",
                daemon=True,
            ).start()
            self._started = True

        if not self._wait_for_server():
            logging.error("Dashboard server did not start on %s", DASHBOARD_URL)

    def _wait_for_server(self, timeout_sec: float = 45.0) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(DASHBOARD_URL, timeout=1.5) as resp:
                    if resp.status == 200:
                        return True
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(0.4)
        return False

    def open_active_plan(self, _icon: pystray.Icon | None = None, _item=None) -> None:
        self.show_dashboard()
        if self.window is not None:
            try:
                self.window.evaluate_js("location.hash='#/plan';")
            except Exception as ex:
                logging.warning("Could not navigate to plan page: %s", ex)

    def open_settings(self, _icon: pystray.Icon | None = None, _item=None) -> None:
        self.show_dashboard()
        if self.window is not None:
            try:
                self.window.evaluate_js("location.hash='#/settings';")
            except Exception as ex:
                logging.warning("Could not navigate to settings page: %s", ex)

    def open_guide(self, _icon: pystray.Icon | None = None, _item=None) -> None:
        self.show_dashboard()
        if self.window is not None:
            try:
                self.window.evaluate_js("location.hash='#/guide';")
            except Exception as ex:
                logging.warning("Could not navigate to guide page: %s", ex)

    def open_bot_guide(self, _icon: pystray.Icon | None = None, _item=None) -> None:
        self.show_dashboard()
        if self.window is not None:
            try:
                self.window.evaluate_js("location.hash='#/bot-guide';")
            except Exception as ex:
                logging.warning("Could not navigate to bot guide: %s", ex)

    def open_selection_guide(self, _icon: pystray.Icon | None = None, _item=None) -> None:
        self.show_dashboard()
        if self.window is not None:
            try:
                self.window.evaluate_js("location.hash='#/selection';")
            except Exception as ex:
                logging.warning("Could not navigate to selection guide: %s", ex)

    def _poll_inbox_notifications(self) -> None:
        while True:
            time.sleep(30)
            try:
                with urllib.request.urlopen(f"{DASHBOARD_URL}api/inbox/summary", timeout=3) as resp:
                    data = json.loads(resp.read().decode())
                unread = int(data.get("unread", 0))
                pending = data.get("pending_plan_day")
                if pending and unread > self._last_inbox_unread:
                    logging.info("New plan pending approval: %s", pending)
                    self.show_dashboard()
                    if self.window is not None:
                        try:
                            self.window.evaluate_js("location.hash='#/plan';")
                        except Exception:
                            pass
                self._last_inbox_unread = unread
            except Exception:
                pass

    def show_dashboard(self, _icon: pystray.Icon | None = None, _item=None) -> None:
        if self.window is None:
            return
        self.window.show()
        try:
            self.window.restore()
        except Exception:
            pass

    def run_plan_now(self, _icon: pystray.Icon | None = None, _item=None) -> None:
        threading.Thread(target=self._run_plan_now, name="plan-now", daemon=True).start()

    def _run_plan_now(self) -> None:
        try:
            cfg = load_config()
            state = load_state(cfg)
            plan = generate_plan(cfg, state, date.today())
            send_plan_notifications(cfg, plan)
            logging.info("Manual plan generated for %s", plan.get("for_trading_day"))
            self.show_dashboard()
            if self.window is not None:
                try:
                    self.window.evaluate_js("location.hash='#/plan';")
                except Exception:
                    pass
        except Exception as ex:
            logging.exception("Manual plan failed: %s", ex)

    def send_heartbeat_now(self, _icon: pystray.Icon | None = None, _item=None) -> None:
        threading.Thread(target=self._send_heartbeat_now, name="heartbeat-now", daemon=True).start()

    def _send_heartbeat_now(self) -> None:
        try:
            cfg = load_config()
            send_heartbeat(cfg, reason="manual")
            logging.info("Manual heartbeat sent")
        except Exception as ex:
            logging.exception("Manual heartbeat failed: %s", ex)

    def quit_app(self, _icon: pystray.Icon | None = None, _item=None) -> None:
        logging.info("Trading Pulse app exiting")
        if self.tray is not None:
            self.tray.stop()
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
        os._exit(0)

    def _on_window_closing(self) -> bool:
        if self.window is not None:
            self.window.hide()
        return False

    def _build_tray_icon(self) -> pystray.Icon:
        menu = pystray.Menu(
            pystray.MenuItem("פתח דשבורד", self.show_dashboard, default=True),
            pystray.MenuItem("תוכנית פעילה", self.open_active_plan),
            pystray.MenuItem("הגדרות", self.open_settings),
            pystray.MenuItem("חיבור בוט טלגרם", self.open_bot_guide),
            pystray.MenuItem("מדריך טלגרם", self.open_guide),
            pystray.MenuItem("איך בוחרים מניות", self.open_selection_guide),
            pystray.MenuItem("תוכנית עכשיו", self.run_plan_now),
            pystray.MenuItem("Heartbeat", self.send_heartbeat_now),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("יציאה", self.quit_app),
        )
        return pystray.Icon("trading-pulse", create_app_icon(), APP_TITLE, menu)

    def _show_already_running(self) -> None:
        logging.error("Trading Pulse is already running. Check the system tray.")
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    0,
                    "Trading Pulse כבר רץ.\nבדוק את אייקון ה-tray.",
                    APP_TITLE,
                    0x30,
                )
            except Exception:
                pass

    def run(self) -> None:
        if not acquire_instance_lock("app"):
            self._show_already_running()
            return

        self.start_background_services()

        self.window = webview.create_window(
            APP_TITLE,
            self.dashboard_url(),
            width=1280,
            height=860,
            min_size=(960, 640),
            text_select=True,
            hidden=self._start_hidden,
        )
        self.window.events.closing += self._on_window_closing

        self.tray = self._build_tray_icon()
        threading.Thread(target=self.tray.run, name="tray", daemon=True).start()
        threading.Thread(target=self._poll_inbox_notifications, name="inbox-poll", daemon=True).start()

        try:
            webview.start(gui="edgechromium")
        except Exception as ex:
            logging.warning("Edge WebView2 unavailable (%s), using default renderer", ex)
            webview.start()
        self.quit_app()


def create_app_icon(size: int = 64) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size // 8
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=size // 5,
        fill=(10, 10, 24, 255),
        outline=(0, 240, 255, 255),
        width=max(2, size // 24),
    )
    bolt = [
        (size * 0.52, size * 0.22),
        (size * 0.38, size * 0.52),
        (size * 0.48, size * 0.52),
        (size * 0.42, size * 0.78),
        (size * 0.66, size * 0.42),
        (size * 0.52, size * 0.42),
    ]
    draw.polygon(bolt, fill=(255, 45, 149, 255))
    return image


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Trading Pulse desktop app")
    parser.add_argument(
        "--tray-only",
        action="store_true",
        help="Start minimized to tray (for Windows login startup)",
    )
    args = parser.parse_args()
    TradingPulseApp(start_hidden=args.tray_only).run()


if __name__ == "__main__":
    main()
