"""Local KB retrieval stub over synthetic markdown (no Bedrock yet)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_KB_ROOT = Path(__file__).resolve().parents[2] / "data" / "knowledge_base"
_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_doc(path: Path) -> dict[str, Any] | None:
    raw = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER.match(raw)
    if not match:
        return {
            "doc_id": path.stem,
            "title": path.stem,
            "body": raw.strip(),
            "policy_type": "unknown",
        }
    meta_block, body = match.groups()
    meta: dict[str, str] = {}
    for line in meta_block.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return {
        "doc_id": meta.get("doc_id", path.stem),
        "title": meta.get("title", path.stem),
        "policy_type": meta.get("policy_type", "unknown"),
        "product_sku": meta.get("product_sku"),
        "body": body.strip(),
    }


def retrieve(message: str, task_type: str, limit: int = 2) -> list[dict[str, Any]]:
    """Keyword-overlap retrieve against local synthetic KB files."""
    if not _KB_ROOT.is_dir():
        return []

    tokens = {t.lower() for t in re.findall(r"[a-zA-Z0-9]+", message) if len(t) > 2}
    scored: list[tuple[int, dict[str, Any]]] = []

    for path in sorted(_KB_ROOT.glob("*.md")):
        doc = _parse_doc(path)
        if doc is None:
            continue
        hay = f"{doc['title']} {doc['body']} {doc.get('policy_type', '')}".lower()
        score = sum(1 for t in tokens if t in hay)
        if task_type in ("faq_policy", "return_request", "refund_request") and doc.get(
            "policy_type"
        ) in ("returns", "faq", "warranty"):
            score += 1
        if task_type == "product_question" and doc.get("policy_type") == "faq":
            score += 1
        if score > 0:
            excerpt = doc["body"][:240].replace("\n", " ").strip()
            scored.append(
                (
                    score,
                    {
                        "doc_id": doc["doc_id"],
                        "title": doc["title"],
                        "excerpt": excerpt,
                        "score": score,
                    },
                )
            )

    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:limit]]
