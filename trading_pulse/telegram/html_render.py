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
        return _crop_bottom_padding(png_path.read_bytes())


def _crop_bottom_padding(png_bytes: bytes, *, bg_threshold: int = 18) -> bytes:
    """Trim empty dark space below the card (viewport taller than content)."""
    from io import BytesIO

    from PIL import Image

    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    pixels = img.load()
    w, h = img.size
    bottom = h - 1
    while bottom > 40:
        row_dark = True
        for x in range(0, w, max(1, w // 40)):
            r, g, b = pixels[x, bottom]
            if r > bg_threshold or g > bg_threshold or b > bg_threshold:
                row_dark = False
                break
        if not row_dark:
            break
        bottom -= 1
    crop_h = min(h, bottom + 24)
    if crop_h >= h - 8:
        return png_bytes
    out = BytesIO()
    img.crop((0, 0, w, crop_h)).save(out, format="PNG", optimize=True)
    return out.getvalue()


def try_render_html_to_png(html: str, **kwargs) -> bytes | None:
    try:
        return render_html_to_png(html, **kwargs)
    except Exception as ex:
        logging.warning("HTML card render failed: %s", ex)
        return None
