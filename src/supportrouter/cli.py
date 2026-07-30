"""CLI for SupportRouter chat and supervisor HITL decisions (#16)."""

from __future__ import annotations

import argparse
import json
import sys

from supportrouter.graph import run_agent
from supportrouter.sessions import decide_hitl, list_sessions, save_session


def handle_message(
    message: str,
    session_id: str | None = None,
    *,
    runtime_mode: str | None = None,
) -> dict:
    result = run_agent(message, session_id=session_id, runtime_mode=runtime_mode)
    return save_session(result)


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    subcommands = {"chat", "list-pending", "decide"}

    # Backward-compatible chat: `python -m supportrouter.cli "message..."`
    if not argv or argv[0] not in subcommands:
        parser = argparse.ArgumentParser(
            description="SupportRouter CLI (VoltEdge synthetic)"
        )
        parser.add_argument("message", nargs="+", help="Customer support message")
        parser.add_argument(
            "--session-id",
            default=None,
            help="Optional session id to continue an existing conversation",
        )
        parser.add_argument(
            "--runtime-mode",
            choices=["local", "aws"],
            default=None,
            help="local (default) or aws Bedrock/tools/KB path",
        )
        args = parser.parse_args(argv)
        result = handle_message(
            " ".join(args.message),
            session_id=args.session_id,
            runtime_mode=args.runtime_mode,
        )
        _print_json(result)
        return 0

    parser = argparse.ArgumentParser(
        description="SupportRouter CLI (VoltEdge synthetic)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat", help="Run one customer support turn")
    chat.add_argument("message", nargs="+", help="Customer support message")
    chat.add_argument("--session-id", default=None)
    chat.add_argument(
        "--runtime-mode",
        choices=["local", "aws"],
        default=None,
        help="local (default) or aws Bedrock/tools/KB path",
    )
    sub.add_parser(
        "list-pending",
        help="List sessions awaiting refund approval or escalation review",
    )

    decide = sub.add_parser(
        "decide",
        help="Approve or reject a pending refund approval (execution stays not_executed)",
    )
    decide.add_argument("session_id", help="Session id with a pending ApprovalRequest")
    decide.add_argument(
        "decision",
        choices=["approve", "reject"],
        help="Supervisor decision",
    )
    decide.add_argument("--note", default="", help="Optional decision note")
    decide.add_argument(
        "--decided-by",
        default="cli-supervisor",
        help="Supervisor identity recorded on the ApprovalRequest",
    )

    args = parser.parse_args(argv)
    if args.command == "chat":
        result = handle_message(
            " ".join(args.message),
            session_id=args.session_id,
            runtime_mode=args.runtime_mode,
        )
        _print_json(result)
        return 0

    if args.command == "list-pending":
        queue = list_sessions(statuses={"pending_approval", "escalated"})
        _print_json(
            [
                {
                    "session_id": item.get("session_id"),
                    "status": item.get("status"),
                    "task_type": item.get("task_type"),
                    "approval_id": item.get("approval_id"),
                    "approval_status": item.get("approval_status"),
                    "refund_amount_usd": item.get("refund_amount_usd"),
                    "hitl_reason": item.get("hitl_reason"),
                }
                for item in queue
            ]
        )
        return 0

    try:
        updated = decide_hitl(
            args.session_id,
            args.decision,
            note=args.note,
            decided_by=args.decided_by,
        )
    except (KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_json(
        {
            "session_id": updated.get("session_id"),
            "status": updated.get("status"),
            "approval_id": updated.get("approval_id"),
            "approval_status": updated.get("approval_status"),
            "hitl_decision": updated.get("hitl_decision"),
            "execution_note": "No refund was executed; execution_status remains not_executed.",
            "answer": updated.get("answer"),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
