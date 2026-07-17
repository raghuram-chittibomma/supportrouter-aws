"""Knowledge retrieval with a local default and explicit Bedrock KB adapter."""

from __future__ import annotations

import os
import re
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

_KB_ROOT = Path(__file__).resolve().parents[2] / "data" / "knowledge_base"
_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_MANAGED_DOC_ID = re.compile(r"\bdoc_id:\s*([a-zA-Z0-9_-]+)")
_MANAGED_TITLE = re.compile(r"\btitle:\s*(.+?)\s+---(?:\s|$)")
_BEDROCK_RETRIEVER = "bedrock"


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


def _retrieve_local(
    message: str,
    task_type: str,
    limit: int,
) -> list[dict[str, Any]]:
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


def _bedrock_client():
    import boto3

    return boto3.client("bedrock-agent-runtime")


def _doc_id_from_result(result: dict[str, Any]) -> str:
    text = result.get("content", {}).get("text", "")
    if isinstance(text, str):
        match = _MANAGED_DOC_ID.search(text)
        if match:
            return match.group(1)
    uri = (
        result.get("location", {})
        .get("s3Location", {})
        .get("uri", "")
    )
    if not isinstance(uri, str) or not uri:
        return "unknown"
    return PurePosixPath(urlparse(uri).path).stem or "unknown"


def _managed_title_and_body(text: str, doc_id: str) -> tuple[str, str]:
    title_match = _MANAGED_TITLE.search(text)
    title = title_match.group(1).strip() if title_match else doc_id
    if text.startswith("---"):
        front_matter_end = text.find("---", 3)
        if front_matter_end >= 0:
            return title, text[front_matter_end + 3 :].strip()
    return title, text.strip()


def _retrieve_bedrock(
    message: str,
    *,
    knowledge_base_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    response = _bedrock_client().retrieve(
        knowledgeBaseId=knowledge_base_id,
        retrievalQuery={"text": message},
        retrievalConfiguration={
            "vectorSearchConfiguration": {"numberOfResults": limit}
        },
    )
    citations: list[dict[str, Any]] = []
    for result in response.get("retrievalResults", []):
        text = result.get("content", {}).get("text", "")
        if not isinstance(text, str):
            text = ""
        doc_id = _doc_id_from_result(result)
        title, body = _managed_title_and_body(text, doc_id)
        citations.append(
            {
                "doc_id": doc_id,
                "title": title,
                "excerpt": body[:240].replace("\n", " ").strip(),
                "score": float(result.get("score") or 0.0),
            }
        )
    return citations


def retrieve(message: str, task_type: str, limit: int = 2) -> list[dict[str, Any]]:
    """Retrieve citations using the configured provider.

    Local deterministic retrieval remains the default. Set
    ``SUPPORTROUTER_RETRIEVER=bedrock`` and ``SUPPORTROUTER_KB_ID`` to use the
    managed Knowledge Base. A configured Bedrock failure is surfaced rather
    than silently falling back to local results. ``task_type`` influences only
    local keyword ranking; managed retrieval uses semantic similarity.
    """
    provider = (
        os.environ.get("SUPPORTROUTER_RETRIEVER", "local").strip().lower()
        or "local"
    )
    if provider == "local":
        return _retrieve_local(message, task_type, limit)
    if provider != _BEDROCK_RETRIEVER:
        raise ValueError(
            "SUPPORTROUTER_RETRIEVER must be 'local' or 'bedrock'"
        )

    knowledge_base_id = os.environ.get("SUPPORTROUTER_KB_ID", "").strip()
    if not knowledge_base_id:
        raise RuntimeError(
            "SUPPORTROUTER_KB_ID is required when "
            "SUPPORTROUTER_RETRIEVER=bedrock"
        )
    return _retrieve_bedrock(
        message,
        knowledge_base_id=knowledge_base_id,
        limit=limit,
    )
