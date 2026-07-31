"""Publish a routing-table JSON into DynamoDB RoutingTable (ADR-023).

Usage:
  python scripts/publish_routing_table.py
  python scripts/publish_routing_table.py --table-name supportrouter-routingtable
  python scripts/publish_routing_table.py --routing-table path/to/table.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROUTING = ROOT / "data" / "sample" / "routing_table.json"

sys.path.insert(0, str(ROOT / "src"))

from supportrouter.routing_dynamo import (  # noqa: E402
    ROUTING_TABLE_ENV,
    publish_routing_table,
)


def _stack_outputs(stack_name: str) -> dict[str, str]:
    try:
        raw = subprocess.check_output(
            [
                "aws",
                "cloudformation",
                "describe-stacks",
                "--stack-name",
                stack_name,
                "--query",
                "Stacks[0].Outputs",
                "--output",
                "json",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        items = json.loads(raw) or []
        return {i["OutputKey"]: i["OutputValue"] for i in items}
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return {}


def resolve_table_name(explicit: str | None) -> str | None:
    return (
        explicit
        or os.environ.get(ROUTING_TABLE_ENV)
        or _stack_outputs("SupportRouter-Api").get("RoutingTableName")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--routing-table",
        type=Path,
        default=DEFAULT_ROUTING,
        help="Runtime-ready routing JSON (default: data/sample/routing_table.json)",
    )
    parser.add_argument("--table-name", default=None)
    args = parser.parse_args(argv)

    table_name = resolve_table_name(args.table_name)
    if not table_name:
        print(
            "No RoutingTable name. Deploy SupportRouter-Api or pass --table-name / "
            f"set {ROUTING_TABLE_ENV}.",
            file=sys.stderr,
        )
        return 2

    document = json.loads(args.routing_table.read_text(encoding="utf-8"))
    os.environ[ROUTING_TABLE_ENV] = table_name
    summary = publish_routing_table(document, table_name=table_name)
    print(json.dumps({"published": summary, "source": str(args.routing_table)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
