#!/usr/bin/env python3
"""beforeShellExecution: block a few high-risk git/secret foot-guns."""
from __future__ import annotations

import json
import re
import sys


def decide(command: str) -> dict:
    c = command.strip()
    low = c.lower()

    # Force-push to main/master
    if re.search(r"\bgit\s+push\b", low) and re.search(r"\s--force(-\w+)?\b|\s-f\b", low):
        if re.search(r"\b(main|master)\b", low) or not re.search(r"\borigin\s+\S+", low):
            return {
                "permission": "deny",
                "user_message": "Blocked: force-push to main/master (or ambiguous force push).",
                "agent_message": "Do not force-push protected branches. Ask the user explicitly.",
            }

    # Hard reset / clean that wipes work
    if re.search(r"\bgit\s+reset\s+--hard\b", low) or re.search(r"\bgit\s+clean\s+-[a-z]*f", low):
        return {
            "permission": "ask",
            "user_message": "Destructive git wipe — confirm before continuing.",
            "agent_message": "Ask the user before git reset --hard / git clean -f.",
        }

    # Staging secrets
    if re.search(r"\bgit\s+add\b", low) and re.search(
        r"(^|[\s/\\])(\.env|instance[/\\]\.env|.*credentials\.json)(\s|$)",
        low,
    ):
        return {
            "permission": "deny",
            "user_message": "Blocked: refusing to git-add .env / credentials.",
            "agent_message": "Never stage secrets. Use config.example / .env.example only.",
        }

    if re.search(r"\bgit\s+commit\b", low) and re.search(r"\b(no-verify|n)\b|--no-gpg-sign", low):
        return {
            "permission": "ask",
            "user_message": "Commit skips hooks/signing — confirm.",
            "agent_message": "Avoid --no-verify unless the user explicitly requested it.",
        }

    return {"permission": "allow"}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        json.dump({"permission": "allow"}, sys.stdout)
        sys.stdout.write("\n")
        return
    command = str(payload.get("command") or "")
    json.dump(decide(command), sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
