#!/usr/bin/env python3
"""sessionStart: inject a short Trading Pulse agent map."""
from __future__ import annotations

import json
import sys


CONTEXT = """Trading Pulse tooling:
- AGENTS.md — agent map + feature pipeline
- @trading-pulse-cracker — runtime forensics (logs/plans)
- @trading-pulse-bot-messages / guide-updater / test-writer / verifier — after code changes
- Never commit instance/.env or bot tokens; runtime data under instance/data/
"""


def main() -> None:
    try:
        json.load(sys.stdin)
    except Exception:
        pass
    json.dump({"additional_context": CONTEXT.strip()}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
