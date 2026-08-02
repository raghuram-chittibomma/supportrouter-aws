#!/usr/bin/env python3
"""Cursor `beforeShellExecution` hook: before a PR is actually merged via the
`gh` CLI, ask for confirmation that the required independent review happened
(see this project's own AGENTS.md > "Before merging a PR").

`gh pr merge` isn't a git command, so it isn't caught by any git-specific
safety hook; this exists to catch that one specific gap.

Sourced from enterprise-sdlc-mcp's templates/new-project/.cursor/ scaffold —
see that repo's ROLLOUT.md "Hooks" section for how to pick up future updates
(hooks don't travel via `pip install -e`, only agents/skills do).

Registered in .cursor/hooks.json (project-level: shared via version control,
so every contributor and every AI agent working in this repo gets it).
"""

from __future__ import annotations

import json
import sys

REVIEW_REMINDER = (
    "Before merging: has an independent Code Reviewer subagent (fresh context, not "
    'self-review) reviewed this PR using get_agent("code-reviewer") + '
    'get_skill("pr-code-review") (or the independent_code_review prompt), with '
    'findings addressed or explicitly deferred, per AGENTS.md > "Before merging a PR"? '
    "Confirm before merging."
)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print(json.dumps({"permission": "allow"}))
        return

    command = (payload.get("command") or "").lower()
    if "gh pr merge" not in command:
        print(json.dumps({"permission": "allow"}))
        return

    print(
        json.dumps(
            {
                "permission": "ask",
                "user_message": REVIEW_REMINDER,
                "agent_message": REVIEW_REMINDER,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({"permission": "allow"}))
