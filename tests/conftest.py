"""Global test isolation for provider-backed integrations."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_to_local_retrieval(monkeypatch):
    """Prevent ordinary tests from making billable managed retrieval calls."""
    monkeypatch.setenv("SUPPORTROUTER_RETRIEVER", "local")
    monkeypatch.delenv("SUPPORTROUTER_KB_ID", raising=False)
