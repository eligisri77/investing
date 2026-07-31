"""Build the public, static demo site under `docs/` for GitHub Pages.

Renders the same "how it works" guide content shown in the live desktop app's
dashboard (`#/selection`, `#/guide`, `#/bot-guide`), but as a snapshot built
from `instance/config.example.json` — generic example settings, never the
user's real live config/state. The output has zero connection to any running
app instance: no live server, no financial data, no personal settings.

Run manually whenever the guide content or example config changes:

    .venv\\Scripts\\python.exe scripts\\build_public_guides.py

Then commit the regenerated files under `docs/`.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from trading_pulse.guides.selection_guide import get_selection_guide
from trading_pulse.telegram.telegram_bot_guide import get_telegram_bot_guide
from trading_pulse.telegram.telegram_guide import get_telegram_guide

DOCS_DIR = REPO_ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"
EXAMPLE_CONFIG = REPO_ROOT / "instance" / "config.example.json"


def _load_example_config() -> dict:
    raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def main() -> None:
    cfg = _load_example_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    guides = {
        "selection.json": get_selection_guide(cfg),
        "telegram.json": get_telegram_guide(cfg),
        "bot.json": get_telegram_bot_guide(),
    }
    for filename, payload in guides.items():
        out = DATA_DIR / filename
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {out.relative_to(REPO_ROOT)}")

    shutil.copyfile(REPO_ROOT / "web" / "static" / "style.css", DOCS_DIR / "style.css")
    print(f"wrote {(DOCS_DIR / 'style.css').relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
