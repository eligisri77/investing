# Installer — for developers

Build a **Windows installer** for users who do not use git.

## Quick build

```powershell
cd path\to\investing
.\.venv\Scripts\pip install -r requirements/requirements.txt
.\installer\build.ps1 -Package
```

Output: `installer\output\TradingPulse-Setup-0.1.0.exe`

Give that single file to users.

## Without Inno Setup

```powershell
.\installer\build.ps1
```

Zip `dist\TradingPulse\` and share — users run `TradingPulse.exe`.

## What gets installed

| Location | Contents |
|----------|----------|
| `%LOCALAPPDATA%\Programs\TradingPulse\` or Inno `{app}` | App binaries + web UI |
| `%LOCALAPPDATA%\TradingPulse\` | `config.json`, `.env`, `data/` (created on first run) |

User secrets and trading data **never** go inside the install folder in git — they live in `%LOCALAPPDATA%\TradingPulse\`.

## First run (automatic)

`bootstrap.py` runs on startup and creates:

- `config.json` from `config.example.json`
- `.env` from `.env.example`
- `data/` folders

User then opens **Settings** or **Bot guide** to connect Telegram.

## Version bump

1. `trading_pulse/core/app_paths.py` → `APP_VERSION`
2. `installer/TradingPulse.iss` → `#define MyAppVersion`
3. Rebuild

## Git vs release

| In git | In release only |
|--------|-----------------|
| Source code, `installer/trading_pulse.spec`, `.iss`, `build.ps1` | `TradingPulse-Setup-*.exe` |
| `instance/config.example.json`, `instance/.env.example` | User's real `config.json`, `.env` |
| | `%LOCALAPPDATA%\TradingPulse\data\` |

Add to `.gitignore`: `dist/`, `build/`, `installer/output/`

See [USER_INSTALL.md](USER_INSTALL.md) — text you can send to end users.
