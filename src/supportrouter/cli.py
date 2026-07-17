"""CLI for SupportRouter LangGraph agent (local stubs)."""

from __future__ import annotations

import argparse
import json
import sys

from supportrouter.graph import run_agent


def handle_message(message: str, session_id: str | None = None) -> dict:
    return run_agent(message, session_id=session_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SupportRouter CLI (VoltEdge synthetic)")
    parser.add_argument("message", nargs="+", help="Customer support message")
    parser.add_argument(
        "--session-id",
        default=None,
        help="Optional session id to continue an existing conversation",
    )
    args = parser.parse_args(argv)
    message = " ".join(args.message)
    result = handle_message(message, session_id=args.session_id)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
