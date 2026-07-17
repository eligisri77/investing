"""In-app updates from GitHub Releases (forward-only, last 3 newer versions)."""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trading_pulse.core.app_paths import APP_VERSION, USER_DATA_DIR, is_frozen

log = logging.getLogger(__name__)

# Public repo that hosts Releases with TradingPulse-Setup-*.exe assets.
DEFAULT_UPDATE_REPO = os.environ.get("TRADING_PULSE_UPDATE_REPO", "eligisri77/investing")
SETUP_ASSET_RE = re.compile(r"^TradingPulse-Setup-[\d.]+\.exe$", re.IGNORECASE)
GITHUB_API = "https://api.github.com"
USER_AGENT = "TradingPulse-Updater"


def _ssl_context() -> ssl.SSLContext:
    """Use certifi CA bundle — Windows/Python embeds often miss system roots."""
    candidates: list[Path] = []
    try:
        import certifi

        candidates.append(Path(certifi.where()))
    except Exception:
        pass
    # PyInstaller may ship cacert next to the bundle
    meipass = getattr(__import__("sys"), "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "certifi" / "cacert.pem")
        candidates.append(Path(meipass) / "cacert.pem")
    for ca in candidates:
        if ca.is_file():
            return ssl.create_default_context(cafile=str(ca))
    return ssl.create_default_context()


def _urlopen(req: urllib.request.Request, *, timeout: float):
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())


@dataclass(frozen=True)
class Version:
    parts: tuple[int, ...]

    @classmethod
    def parse(cls, raw: str) -> Version | None:
        s = str(raw or "").strip()
        if s.lower().startswith("v"):
            s = s[1:]
        if not s or not re.fullmatch(r"\d+(\.\d+)*", s):
            return None
        return cls(tuple(int(p) for p in s.split(".")))

    def __str__(self) -> str:
        return ".".join(str(p) for p in self.parts)

    def __lt__(self, other: Version) -> bool:
        return self._pad() < other._pad()

    def __le__(self, other: Version) -> bool:
        return self._pad() <= other._pad()

    def __gt__(self, other: Version) -> bool:
        return self._pad() > other._pad()

    def __ge__(self, other: Version) -> bool:
        return self._pad() >= other._pad()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._pad() == other._pad()

    def _pad(self) -> tuple[int, ...]:
        p = list(self.parts) + [0, 0, 0]
        return tuple(p[:3])


def current_version() -> Version:
    parsed = Version.parse(APP_VERSION)
    if parsed is None:
        return Version((0, 0, 0))
    return parsed


def _http_get_json(url: str, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with _urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pick_setup_asset(release: dict[str, Any]) -> dict[str, Any] | None:
    assets = release.get("assets") or []
    for asset in assets:
        name = str(asset.get("name") or "")
        if SETUP_ASSET_RE.match(name):
            return asset
    for asset in assets:
        name = str(asset.get("name") or "")
        if name.lower().endswith(".exe") and "setup" in name.lower():
            return asset
    return None


def fetch_github_releases(repo: str | None = None, *, limit: int = 30) -> list[dict[str, Any]]:
    repo = (repo or DEFAULT_UPDATE_REPO).strip()
    url = f"{GITHUB_API}/repos/{repo}/releases?per_page={int(limit)}"
    data = _http_get_json(url)
    if not isinstance(data, list):
        raise RuntimeError("Unexpected GitHub releases response")
    return data


def list_upgrade_options(
    *,
    current: Version | None = None,
    repo: str | None = None,
    max_options: int = 3,
) -> dict[str, Any]:
    """Return up to `max_options` newer releases (newest first). Forward-only."""
    cur = current or current_version()
    repo = (repo or DEFAULT_UPDATE_REPO).strip()
    payload: dict[str, Any] = {
        "current_version": str(cur),
        "repo": repo,
        "frozen": is_frozen(),
        "upgrades": [],
        "latest": None,
        "message": None,
    }
    try:
        releases = fetch_github_releases(repo)
    except urllib.error.HTTPError as ex:
        if ex.code == 404:
            payload["message"] = "לא נמצאו Releases בריפו — פרסמו Setup.exe ב-GitHub Releases"
            return payload
        payload["message"] = f"שגיאה מ-GitHub ({ex.code})"
        return payload
    except Exception as ex:
        log.warning("update check failed: %s", ex)
        payload["message"] = f"לא ניתן לבדוק עדכונים: {ex}"
        return payload

    upgrades: list[dict[str, Any]] = []
    for rel in releases:
        if rel.get("draft") or rel.get("prerelease"):
            continue
        tag = str(rel.get("tag_name") or "")
        ver = Version.parse(tag)
        if ver is None:
            continue
        if ver <= cur:
            continue
        asset = _pick_setup_asset(rel)
        if not asset:
            continue
        upgrades.append(
            {
                "version": str(ver),
                "tag": tag,
                "name": rel.get("name") or tag,
                "published_at": rel.get("published_at"),
                "notes": (rel.get("body") or "")[:2000],
                "download_url": asset.get("browser_download_url"),
                "asset_name": asset.get("name"),
                "size_bytes": asset.get("size"),
            }
        )
        if len(upgrades) >= max_options:
            break

    payload["upgrades"] = upgrades
    payload["latest"] = upgrades[0] if upgrades else None
    if not upgrades:
        payload["message"] = "אין גרסה חדשה יותר מהנוכחית"
    return payload


def _download_file(url: str, dest: Path, *, timeout: float = 120.0) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _urlopen(req, timeout=timeout) as resp, open(dest, "wb") as out:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)


def download_and_launch_installer(
    version: str,
    *,
    repo: str | None = None,
) -> dict[str, Any]:
    """Download a newer Setup.exe and start it. Forward-only."""
    target = Version.parse(version)
    if target is None:
        raise ValueError("גרסה לא תקינה")

    options = list_upgrade_options(repo=repo, max_options=3)
    match = next((u for u in options["upgrades"] if Version.parse(u["version"]) == target), None)
    if not match:
        raise ValueError("הגרסה לא זמינה לשדרוג (רק קדימה, מתוך 3 האחרונות)")

    url = str(match["download_url"] or "")
    if not url:
        raise ValueError("חסר קישור הורדה")

    asset_name = str(match["asset_name"] or f"TradingPulse-Setup-{target}.exe")
    download_dir = USER_DATA_DIR / "updates"
    download_dir.mkdir(parents=True, exist_ok=True)
    dest = download_dir / asset_name

    log.info("Downloading update %s → %s", target, dest)
    _download_file(url, dest)

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )
    subprocess.Popen(
        [str(dest)],
        cwd=str(dest.parent),
        close_fds=True,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )

    return {
        "ok": True,
        "version": str(target),
        "installer_path": str(dest),
        "message": "המתקין נפתח. סגרו את Trading Pulse מה-tray ואשרו את ההתקנה.",
    }
