# PyInstaller spec — build with: pyinstaller installer/trading_pulse.spec
# Output: dist/TradingPulse/TradingPulse.exe

import sys
from pathlib import Path

block_cipher = None
# SPECPATH = directory containing this .spec (installer/), so repo root is parent.
_spec_dir = Path(SPECPATH)
root = _spec_dir.parent if _spec_dir.name == "installer" else _spec_dir.parent.parent
if not (root / "trading_pulse" / "desktop" / "win_app.py").is_file():
    raise SystemExit(f"Repo root not found from SPECPATH={SPECPATH!r} (resolved root={root})")

datas = [
    (str(root / "web" / "static"), "web/static"),
    (str(root / "instance" / "config.example.json"), "."),
    (str(root / "instance" / ".env.example"), "."),
]

try:
    import certifi

    datas.append((certifi.where(), "certifi"))
except Exception:
    pass

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "dotenv",
    "certifi",
]

a = Analysis(
    [str(root / "trading_pulse" / "desktop" / "win_app.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_icon = root / "installer" / "assets" / "TradingPulse.ico"
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TradingPulse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_icon) if _icon.is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TradingPulse",
)
