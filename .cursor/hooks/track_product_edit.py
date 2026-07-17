#!/usr/bin/env python3
"""afterFileEdit: mark product edits that still need tests/guides."""
from __future__ import annotations

import json
import sys

from ship_state import note_edit


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    path = str(payload.get("file_path") or "")
    if path:
        note_edit(path)
    # afterFileEdit is observational — empty object is fine
    json.dump({}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
