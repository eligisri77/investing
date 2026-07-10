"""HTML card templates for Telegram photo messages (dashboard look)."""

from __future__ import annotations

import html as html_lib
from typing import Any

_CSS = """
:root {
  --bg: #07070f;
  --surface: rgba(18, 18, 32, 0.92);
  --border: rgba(255, 255, 255, 0.08);
  --text: #f4f4ff;
  --muted: #9da3c2;
  --pink: #ff2d95;
  --cyan: #00f0ff;
  --purple: #a855f7;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  background: var(--bg);
  color: var(--text);
  font-family: "Segoe UI", "Arial Hebrew", Arial, sans-serif;
  direction: rtl;
  width: 420px;
}
body {
  padding: 22px 14px 26px;
  background:
    radial-gradient(ellipse 280px 220px at 100% -10%, rgba(255,45,149,0.22), transparent 60%),
    radial-gradient(ellipse 240px 200px at -10% 110%, rgba(0,240,255,0.14), transparent 55%),
    var(--bg);
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 18px 14px 14px;
}
.header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}
.accent {
  width: 4px;
  height: 28px;
  border-radius: 4px;
  background: linear-gradient(var(--pink), var(--purple));
  flex-shrink: 0;
}
.accent.cyan { background: linear-gradient(var(--cyan), var(--purple)); }
h1 {
  font-size: 19px;
  font-weight: 800;
  letter-spacing: -0.02em;
}
.sub {
  color: var(--muted);
  font-size: 12px;
  margin-top: 4px;
  line-height: 1.4;
}
.flow { display: flex; flex-direction: column; gap: 0; margin-top: 4px; }
.step {
  display: grid;
  grid-template-columns: 92px 1fr;
  gap: 10px;
  position: relative;
  padding-bottom: 16px;
}
.step:last-child { padding-bottom: 0; }
.marker {
  font-weight: 800;
  font-size: 11px;
  color: var(--cyan);
  background: rgba(0, 240, 255, 0.08);
  border: 1px solid rgba(0, 240, 255, 0.28);
  border-radius: 10px;
  padding: 8px 6px;
  text-align: center;
  line-height: 1.3;
  align-self: start;
  white-space: pre-line;
}
.title { font-weight: 700; font-size: 14px; margin-top: 2px; }
.detail { color: var(--muted); font-size: 12px; margin-top: 4px; line-height: 1.45; }
.line {
  position: absolute;
  right: 45px;
  top: 44px;
  bottom: 0;
  width: 2px;
  background: linear-gradient(var(--cyan), transparent);
  opacity: 0.35;
}
.step:last-child .line { display: none; }
.cmd-grid { display: flex; flex-direction: column; gap: 8px; margin-top: 6px; }
.cmd-row {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  background: rgba(7, 7, 15, 0.55);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 11px 12px;
}
.chip {
  font-family: Consolas, "Cascadia Mono", monospace;
  font-weight: 700;
  font-size: 12px;
  color: var(--pink);
  background: rgba(255, 45, 149, 0.1);
  border: 1px solid rgba(255, 45, 149, 0.28);
  border-radius: 8px;
  padding: 5px 9px;
  white-space: normal;
  word-break: break-word;
  align-self: flex-start;
}
.desc { color: var(--text); font-size: 13px; line-height: 1.4; }
.start-grid { display: flex; flex-direction: column; gap: 12px; margin-top: 6px; }
.start-card {
  background: rgba(7, 7, 15, 0.55);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px 16px;
}
.start-head { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 8px; }
.start-icon { font-size: 22px; line-height: 1; }
.start-title { font-weight: 700; font-size: 15px; }
.start-detail { color: var(--muted); font-size: 13px; margin-top: 3px; line-height: 1.4; }
.tips { margin-top: 6px; display: flex; flex-direction: column; gap: 8px; }
.tip {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.45;
  padding: 10px 12px;
  background: rgba(7, 7, 15, 0.45);
  border: 1px solid var(--border);
  border-radius: 12px;
}
.tip::before { content: "💡 "; }
"""


def _esc(text: Any) -> str:
    return html_lib.escape(str(text or ""))


def _wrap(body: str) -> str:
    return (
        "<!DOCTYPE html><html lang='he'><head><meta charset='utf-8'>"
        f"<style>{_CSS}</style></head><body>{body}</body></html>"
    )


CARD_WIDTH = 420


def estimate_height(kind: str, n_items: int) -> int:
    """Taller estimates — narrow cards wrap more text."""
    base = 140
    if kind == "flow":
        return min(2800, base + n_items * 130)
    if kind == "commands":
        return min(3200, base + n_items * 92)
    if kind == "start":
        return min(2000, base + n_items * 120)
    if kind == "tips":
        return min(2200, base + n_items * 72)
    return 1200


def guide_flow_html(title: str, flow: list[dict[str, Any]], *, subtitle: str = "") -> str:
    steps = []
    for item in flow:
        time_txt = str(item.get("time", "")).replace(" | ", "\n")
        steps.append(
            "<div class='step'>"
            f"<div class='marker'>{_esc(time_txt)}</div>"
            "<div>"
            f"<div class='title'>{_esc(item.get('label', ''))}</div>"
            f"<div class='detail'>{_esc(item.get('detail', ''))}</div>"
            "</div>"
            "<div class='line'></div>"
            "</div>"
        )
    sub = f"<div class='sub'>{_esc(subtitle)}</div>" if subtitle else ""
    body = (
        "<div class='card'>"
        "<div class='header'><div class='accent cyan'></div>"
        f"<div><h1>{_esc(title)}</h1>{sub}</div></div>"
        f"<div class='flow'>{''.join(steps)}</div>"
        "</div>"
    )
    return _wrap(body)


def guide_commands_html(title: str, items: list[dict[str, Any]], *, warning: str = "") -> str:
    rows = []
    for item in items:
        rows.append(
            "<div class='cmd-row'>"
            f"<code class='chip'>{_esc(item.get('cmd', ''))}</code>"
            f"<div class='desc'>{_esc(item.get('desc', ''))}</div>"
            "</div>"
        )
    warn = f"<div class='sub' style='color:#ffe600;margin-bottom:10px'>⚠️ {_esc(warning)}</div>" if warning else ""
    body = (
        "<div class='card'>"
        "<div class='header'><div class='accent'></div>"
        f"<div><h1>{_esc(title)}</h1></div></div>"
        f"{warn}<div class='cmd-grid'>{''.join(rows)}</div>"
        "</div>"
    )
    return _wrap(body)


def guide_start_html(title: str, items: list[dict[str, Any]], *, subtitle: str = "") -> str:
    cards = []
    for item in items:
        cmd = item.get("cmd")
        chip = f"<div style='margin-top:10px'><code class='chip'>{_esc(cmd)}</code></div>" if cmd else ""
        cards.append(
            "<div class='start-card'>"
            "<div class='start-head'>"
            f"<span class='start-icon'>{_esc(item.get('icon', '📌'))}</span>"
            "<div>"
            f"<div class='start-title'>{_esc(item.get('title', ''))}</div>"
            f"<div class='start-detail'>{_esc(item.get('detail', ''))}</div>"
            f"{chip}"
            "</div></div></div>"
        )
    sub = f"<div class='sub'>{_esc(subtitle)}</div>" if subtitle else ""
    body = (
        "<div class='card'>"
        "<div class='header'><div class='accent'></div>"
        f"<div><h1>{_esc(title)}</h1>{sub}</div></div>"
        f"<div class='start-grid'>{''.join(cards)}</div>"
        "</div>"
    )
    return _wrap(body)


def guide_tips_html(title: str, tips: list[str]) -> str:
    rows = "".join(f"<div class='tip'>{_esc(t)}</div>" for t in tips)
    body = (
        "<div class='card'>"
        "<div class='header'><div class='accent cyan'></div>"
        f"<div><h1>{_esc(title)}</h1></div></div>"
        f"<div class='tips'>{rows}</div>"
        "</div>"
    )
    return _wrap(body)
