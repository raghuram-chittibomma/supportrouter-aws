"""Generate / refresh synthetic VoltEdge fixtures (deterministic seed).

Currently fixtures are checked in under data/sample/. This script validates
they load and prints summary counts for local demos.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"


def main() -> None:
    catalog = json.loads((SAMPLE / "catalog.json").read_text(encoding="utf-8"))
    orders = json.loads((SAMPLE / "orders.json").read_text(encoding="utf-8"))
    routing = json.loads((SAMPLE / "routing_table.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "products": len(catalog["products"]),
                "orders": len(orders["orders"]),
                "routes": len(routing["routes"]),
                "routing_table_version": routing["routing_table_version"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
