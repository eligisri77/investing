#!/usr/bin/env python3
"""subagentStop: clear pending tests/guides when specialists finish."""
from __future__ import annotations

import json
import sys

from ship_state import note_subagent


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    note_subagent(
        str(payload.get("subagent_type") or ""),
        str(payload.get("status") or ""),
    )
    json.dump({}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
