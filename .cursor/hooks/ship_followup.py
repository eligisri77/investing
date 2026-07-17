#!/usr/bin/env python3
"""stop: auto-nudge parent agent to run test-writer / guide-updater."""
from __future__ import annotations

import json
import sys

from ship_state import clear_state, load_state, pending_summary


FOLLOWUP = """Ship checklist incomplete after product edits.

Launch these Task subagents now (in parallel if both needed), then briefly report results — do not skip:

{agents}

Do not invent new product scope. After they finish, you may say the feature is done.
"""


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    status = str(payload.get("status") or "")
    loop_count = int(payload.get("loop_count") or 0)

    if status != "completed":
        json.dump({}, sys.stdout)
        sys.stdout.write("\n")
        return

    missing = pending_summary(load_state())
    if not missing:
        json.dump({}, sys.stdout)
        sys.stdout.write("\n")
        return

    # One automatic nudge per ship gap; avoid infinite loops.
    if loop_count >= 1:
        clear_state()
        json.dump({}, sys.stdout)
        sys.stdout.write("\n")
        return

    agents: list[str] = []
    state = load_state()
    if state.get("need_tests"):
        agents.append(
            "- Task subagent_type=`trading-pulse-test-writer` — add/extend pytest for the behavior just changed"
        )
    if state.get("need_guides"):
        agents.append(
            "- Task subagent_type=`trading-pulse-guide-updater` — sync #/guide, user_guide_*, selection if UX/commands changed"
        )

    msg = FOLLOWUP.format(agents="\n".join(agents))
    json.dump({"followup_message": msg.strip()}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
