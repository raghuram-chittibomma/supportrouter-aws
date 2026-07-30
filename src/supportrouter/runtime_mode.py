"""Runtime mode selection: local stubs (default) vs AWS Bedrock path."""

from __future__ import annotations

import os
from typing import Literal

RuntimeMode = Literal["local", "aws"]

ENV_DEFAULT_MODE = "SUPPORTROUTER_RUNTIME_MODE"


def normalize_runtime_mode(value: str | None = None) -> RuntimeMode:
    raw = (
        value
        if value is not None and str(value).strip()
        else os.environ.get(ENV_DEFAULT_MODE, "local")
    )
    mode = str(raw).strip().lower()
    if mode in {"local", "stub", "offline"}:
        return "local"
    if mode in {"aws", "bedrock", "live"}:
        return "aws"
    raise ValueError("runtime_mode must be 'local' or 'aws'")


def default_runtime_mode() -> RuntimeMode:
    return normalize_runtime_mode(None)
