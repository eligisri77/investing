"""Render self-contained HTML cards to PNG via Edge/Chrome headless."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

_BROWSER_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Microsoft"
    / "Edge"
    / "Application"
    / "msedge.exe",
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Microsoft"
    / "Edge"
    / "Application"
    / "msedge.exe",
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Google"
    / "Chrome"
    / "Application"
    / "chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Google"
    / "Chrome"
    / "Application"
    / "chrome.exe",
)


def find_browser() -> Path | None:
    which_edge = shutil.which("msedge")
    which_chrome = shutil.which("chrome") or shutil.which("google-chrome")
    for candidate in (
        *(Path(p) for p in (which_edge, which_chrome) if p),
        *_BROWSER_CANDIDATES,
    ):
        if candidate and candidate.is_file():
            return candidate
    return None


def render_html_to_png(
    html: str,
    *,
    width: int = 420,
    height: int = 1600,
    timeout_sec: float = 25.0,
) -> bytes:
    """Write HTML to a temp file and screenshot with headless Chromium/Edge."""
    browser = find_browser()
    if browser is None:
        raise RuntimeError("No Edge/Chrome found for HTML screenshot")

    with tempfile.TemporaryDirectory(prefix="tp_html_") as tmp:
        tmp_path = Path(tmp)
        html_path = tmp_path / "card.html"
        png_path = tmp_path / "card.png"
        html_path.write_text(html, encoding="utf-8")
        file_url = html_path.resolve().as_uri()

        cmd = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=2",
            f"--window-size={width},{height}",
            f"--screenshot={png_path}",
            file_url,
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if not png_path.exists() or png_path.stat().st_size < 100:
            err = (proc.stderr or proc.stdout or "").strip()[:400]
            raise RuntimeError(f"HTML screenshot failed: {err or 'empty png'}")
        return _crop_to_content(png_path.read_bytes())


def _crop_to_content(
    png_bytes: bytes,
    *,
    bg: tuple[int, int, int] = (10, 10, 24),
    delta: int = 12,
    pad: int = 16,
) -> bytes:
    """Trim empty viewport padding so Telegram does not shrink the card to a speck."""
    from io import BytesIO

    from PIL import Image

    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    pixels = img.load()
    w, h = img.size
    step = max(1, w // 80)

    def _row_has_content(y: int) -> bool:
        br, bg_, bb = bg
        for x in range(0, w, step):
            r, g, b = pixels[x, y]
            if abs(r - br) > delta or abs(g - bg_) > delta or abs(b - bb) > delta:
                return True
        return False

    top = 0
    while top < h - 1 and not _row_has_content(top):
        top += 1
    bottom = h - 1
    while bottom > top and not _row_has_content(bottom):
        bottom -= 1

    y0 = max(0, top - pad)
    y1 = min(h, bottom + pad + 1)
    if y1 - y0 >= h - 4:
        return png_bytes
    out = BytesIO()
    img.crop((0, y0, w, y1)).save(out, format="PNG", optimize=True)
    return out.getvalue()


def try_render_html_to_png(html: str, **kwargs) -> bytes | None:
    try:
        return render_html_to_png(html, **kwargs)
    except Exception as ex:
        logging.warning("HTML card render failed: %s", ex)
        return None
