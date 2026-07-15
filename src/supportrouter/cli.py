"""CLI demo for first slice: classify + route (no Bedrock)."""

from __future__ import annotations

import argparse
import json
import sys
import uuid

from supportrouter.classifier import classify
from supportrouter.router import route
from supportrouter.schemas import SessionRecord


def handle_message(message: str) -> dict:
    classification = classify(message)
    decision = route(classification.task_type)
    session = SessionRecord(
        session_id=str(uuid.uuid4()),
        message=message,
        task_type=classification.task_type,
        model_id=decision.model_id,
        status="classified",
        confidence=classification.confidence,
    )
    return {
        "session_id": session.session_id,
        "task_type": session.task_type,
        "model_id": session.model_id,
        "confidence": session.confidence,
        "classifier_rationale": classification.rationale,
        "routing_table_version": decision.routing_table_version,
        "status": session.status,
        "note": "First slice: no Bedrock call; model_id is seeded routing only.",
    }


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
