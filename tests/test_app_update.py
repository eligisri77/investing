"""Tests for forward-only GitHub update options."""

from __future__ import annotations

from trading_pulse.core import app_update as au


def _release(tag: str, *, setup: bool = True, draft: bool = False) -> dict:
    assets = []
    if setup:
        ver = tag.lstrip("v")
        assets.append(
            {
                "name": f"TradingPulse-Setup-{ver}.exe",
                "browser_download_url": f"https://example.com/{ver}.exe",
                "size": 10_000_000,
            }
        )
    return {
        "tag_name": tag,
        "name": f"Trading Pulse {tag}",
        "published_at": "2026-07-01T00:00:00Z",
        "body": "notes",
        "draft": draft,
        "prerelease": False,
        "assets": assets,
    }


def test_version_compare():
    assert au.Version.parse("1.1.9") > au.Version.parse("1.1.1")
    assert au.Version.parse("v0.1.0") == au.Version.parse("0.1.0")
    assert au.Version.parse("1.2") > au.Version.parse("1.1.9")


def test_list_upgrade_options_last_three_newer_only(monkeypatch):
    releases = [
        _release("v1.1.9"),
        _release("v1.1.8"),
        _release("v1.1.7"),
        _release("v1.1.6"),
        _release("v1.1.1"),
        _release("v1.0.0"),
    ]
    monkeypatch.setattr(au, "fetch_github_releases", lambda repo=None, limit=30: releases)
    out = au.list_upgrade_options(current=au.Version.parse("1.1.1"), max_options=3)
    versions = [u["version"] for u in out["upgrades"]]
    assert versions == ["1.1.9", "1.1.8", "1.1.7"]
    assert out["latest"]["version"] == "1.1.9"


def test_list_upgrade_skips_older_and_no_asset(monkeypatch):
    releases = [
        _release("v1.1.9", setup=False),
        _release("v1.1.8"),
        _release("v1.0.0"),
    ]
    monkeypatch.setattr(au, "fetch_github_releases", lambda repo=None, limit=30: releases)
    out = au.list_upgrade_options(current=au.Version.parse("1.1.1"), max_options=3)
    assert [u["version"] for u in out["upgrades"]] == ["1.1.8"]


def test_no_upgrade_when_already_latest(monkeypatch):
    releases = [_release("v1.1.9"), _release("v1.1.8")]
    monkeypatch.setattr(au, "fetch_github_releases", lambda repo=None, limit=30: releases)
    out = au.list_upgrade_options(current=au.Version.parse("1.1.9"), max_options=3)
    assert out["upgrades"] == []
    assert "אין גרסה חדשה" in (out["message"] or "")


def test_download_rejects_downgrade(monkeypatch):
    releases = [_release("v1.1.9"), _release("v1.1.8")]
    monkeypatch.setattr(au, "fetch_github_releases", lambda repo=None, limit=30: releases)
    try:
        au.download_and_launch_installer("1.1.0")
        assert False, "expected ValueError"
    except ValueError as ex:
        assert "לא זמינה" in str(ex)
