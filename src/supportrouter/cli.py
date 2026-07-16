"""CLI for SupportRouter LangGraph agent (local stubs)."""

from __future__ import annotations

import argparse
import json
import sys

from supportrouter.graph import run_agent


def handle_message(message: str) -> dict:
    return run_agent(message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SupportRouter CLI (VoltEdge synthetic)")
    parser.add_argument("message", nargs="+", help="Customer support message")
    args = parser.parse_args(argv)
    message = " ".join(args.message)
    result = handle_message(message)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
