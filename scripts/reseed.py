"""On-demand reseed: upload KB docs to S3 and start Bedrock ingestion (ADR-008).

Usage:
  python scripts/reseed.py
  python scripts/reseed.py --docs-bucket NAME --kb-id ID --data-source-id ID

If flags are omitted, values are read from env:
  SUPPORTROUTER_DOCS_BUCKET, SUPPORTROUTER_KB_ID, SUPPORTROUTER_DATA_SOURCE_ID
or from ``cdk deploy`` outputs when AWS credentials can describe stacks.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_DIR = ROOT / "data" / "knowledge_base"
SAMPLE_DIR = ROOT / "data" / "sample"


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


def resolve_config(args: argparse.Namespace) -> dict[str, str | None]:
    outs = _stack_outputs("SupportRouter-KnowledgeBase")
    return {
        "docs_bucket": args.docs_bucket
        or os.environ.get("SUPPORTROUTER_DOCS_BUCKET")
        or outs.get("KbDocsBucketName"),
        "kb_id": args.kb_id
        or os.environ.get("SUPPORTROUTER_KB_ID")
        or outs.get("KnowledgeBaseId"),
        "data_source_id": args.data_source_id
        or os.environ.get("SUPPORTROUTER_DATA_SOURCE_ID")
        or outs.get("DataSourceId"),
    }


def upload_kb_docs(bucket: str) -> list[str]:
    uploaded: list[str] = []
    for path in sorted(KB_DIR.glob("*.md")):
        key = f"knowledge_base/{path.name}"
        subprocess.check_call(
            ["aws", "s3", "cp", str(path), f"s3://{bucket}/{key}"],
        )
        uploaded.append(key)
    return uploaded


def start_ingestion(kb_id: str, data_source_id: str) -> None:
    subprocess.check_call(
        [
            "aws",
            "bedrock-agent",
            "start-ingestion-job",
            "--knowledge-base-id",
            kb_id,
            "--data-source-id",
            data_source_id,
        ]
    )


def validate_local_fixtures() -> dict:
    catalog = json.loads((SAMPLE_DIR / "catalog.json").read_text(encoding="utf-8"))
    orders = json.loads((SAMPLE_DIR / "orders.json").read_text(encoding="utf-8"))
    routing = json.loads((SAMPLE_DIR / "routing_table.json").read_text(encoding="utf-8"))
    kb_docs = list(KB_DIR.glob("*.md"))
    return {
        "products": len(catalog["products"]),
        "orders": len(orders["orders"]),
        "routes": len(routing["routes"]),
        "kb_docs": len(kb_docs),
        "routing_table_version": routing["routing_table_version"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SupportRouter on-demand reseed")
    parser.add_argument("--docs-bucket")
    parser.add_argument("--kb-id")
    parser.add_argument("--data-source-id")
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Only validate local fixtures; skip S3/KB calls",
    )
    args = parser.parse_args(argv)

    summary = validate_local_fixtures()
    print(json.dumps({"local_fixtures": summary}, indent=2))

    if args.local_only:
        return 0

    cfg = resolve_config(args)
    if not cfg["docs_bucket"]:
        print(
            "No docs bucket configured. Deploy SupportRouter-KnowledgeBase or pass --docs-bucket. "
            "Use --local-only to validate fixtures without AWS.",
            file=sys.stderr,
        )
        return 2

    uploaded = upload_kb_docs(cfg["docs_bucket"])
    print(json.dumps({"uploaded": uploaded, "bucket": cfg["docs_bucket"]}, indent=2))

    if cfg["kb_id"] and cfg["data_source_id"]:
        start_ingestion(cfg["kb_id"], cfg["data_source_id"])
        print(
            json.dumps(
                {
                    "ingestion_started": True,
                    "kb_id": cfg["kb_id"],
                    "data_source_id": cfg["data_source_id"],
                },
                indent=2,
            )
        )
    else:
        print(
            "KB_ID / DATA_SOURCE_ID missing — docs uploaded; start ingestion manually after deploy.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
