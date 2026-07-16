"""Unit tests for on-demand reseed helper (local-only path)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("reseed", ROOT / "scripts" / "reseed.py")
assert _SPEC and _SPEC.loader
reseed = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(reseed)


def test_validate_local_fixtures():
    summary = reseed.validate_local_fixtures()
    assert summary["products"] == 7
    assert summary["orders"] >= 3
    assert summary["kb_docs"] >= 2


def test_reseed_local_only_exits_zero():
    assert reseed.main(["--local-only"]) == 0
