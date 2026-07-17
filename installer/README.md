# Installer — for developers

Build a **Windows installer** for users who do not use git.

## Quick build

```powershell
cd path\to\investing
.\.venv\Scripts\pip install -r requirements/requirements.txt
.\installer\build.ps1 -Package
```

Output: `installer\output\TradingPulse-Setup-<version>.exe`  
Version comes from `trading_pulse.core.app_paths.APP_VERSION`.

Give that single file to users. The wizard is **Hebrew-first** (English available).

## Without Inno Setup

```powershell
.\installer\build.ps1
```

Zip `dist\TradingPulse\` and share — users run `TradingPulse.exe`.

## What gets installed

| Location | Contents |
|----------|----------|
| `%LOCALAPPDATA%\Programs\TradingPulse\` (`{app}`) | App binaries + web UI |
| `%LOCALAPPDATA%\TradingPulse\` | `config.json`, `.env`, `data/` (created on first run) |

User secrets and trading data **never** go inside the install folder in git — they live in `%LOCALAPPDATA%\TradingPulse\`. Uninstall keeps that folder and shows a reminder.

## Installer features (`TradingPulse.iss`)

- Hebrew wizard + info before/after screens
- Desktop shortcut + optional Windows startup (`--tray-only`)
- App icon on Setup.exe / shortcuts (`installer/assets/TradingPulse.ico`)
- `AppMutex` matches `Local\TradingPulse.SingleInstance` (blocks install while app is running)
- No admin (`PrivilegesRequired=lowest`)

## First run (automatic)

`bootstrap.py` runs on startup and creates:

- `config.json` from `config.example.json`
- `.env` from `.env.example`
- `data/` folders

User then opens **Settings** or **Bot guide** to connect Telegram.

## Publishing a release (for the in-app updater)

1. Bump `APP_VERSION` in `trading_pulse/core/app_paths.py`
2. `.\installer\build.ps1 -Package`
3. Create a GitHub Release tagged `vX.Y.Z` and upload `TradingPulse-Setup-X.Y.Z.exe`

The app settings page lists up to **3 newer** releases (forward-only) from `eligisri77/investing`.

## Version bump

1. Change only `trading_pulse/core/app_paths.py` → `APP_VERSION`
2. Rebuild with `.\installer\build.ps1 -Package` (passes `/DMyAppVersion=…` to Inno)

Manual ISCC: fallback `#define MyAppVersion` inside `TradingPulse.iss`.

## Icon

```powershell
.\.venv\Scripts\python.exe installer\assets\generate_icon.py
```

`build.ps1` regenerates the `.ico` automatically before PyInstaller.

## Git vs release

| In git | In release only |
|--------|-----------------|
| Source, `trading_pulse.spec`, `.iss`, `build.ps1`, `assets/generate_icon.py` | `TradingPulse-Setup-*.exe` |
| `instance/config.example.json`, `instance/.env.example` | User's real `config.json`, `.env` |
| | `%LOCALAPPDATA%\TradingPulse\data\` |

Ignored: `dist/`, `build/`, `installer/output/`

See [USER_INSTALL.md](USER_INSTALL.md) — text you can send to end users.
