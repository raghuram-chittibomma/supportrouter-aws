"""Live Bedrock adapters for the SupportRouter eval harness (#17).

Local-stub execution remains the default. These adapters are selected only when
the harness is run with ``--live`` (or when injected in tests).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from supportrouter.bedrock_converse import converse_text, extract_json_object
from supportrouter.bedrock_models import (
    estimate_cost_usd,
    resolve_inference_profile,
)
from supportrouter.graph import run_agent
from supportrouter.observability import PLANE_EVAL
from supportrouter.prompt_cache import (
    agent_cacheable_prefix,
    converse_system_with_cache_point,
)

from evals.prompt_cache import judge_cacheable_prefix

# Back-compat aliases for harness imports.
LOGICAL_TO_INFERENCE_PROFILE = {
    "logical:nova-micro": "us.amazon.nova-micro-v1:0",
    "logical:nova-lite": "us.amazon.nova-lite-v1:0",
    "logical:claude-haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
}

DEFAULT_JUDGE_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_RUBRIC_PATH = Path(__file__).resolve().parent / "rubrics" / "v0.1_judge.json"


def _draft_user_prompt(scenario: dict[str, Any], local_output: dict[str, Any]) -> str:
    return json.dumps(
        {
            "customer_message": scenario["input"],
            "task_type": local_output.get("task_type"),
            "status": local_output.get("status"),
            "citations": local_output.get("citations") or [],
            "tool_calls": local_output.get("tool_calls") or [],
            "local_stub_answer": local_output.get("answer"),
            "instructions": (
                "Draft a concise VoltEdge Electronics customer support reply using "
                "only the provided synthetic tool results and citations. Do not invent "
                "orders, policies, or amounts. Preserve required HITL/escalation outcomes "
                "implied by status. Do not mention that drafting used Bedrock."
            ),
        },
        indent=2,
    )


class BedrockCandidateRunner:
    """Local graph for tools/retrieve; Bedrock Converse for the candidate draft."""

    execution_mode = "bedrock_converse"

    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client

    def run(self, scenario: dict[str, Any], requested_model_id: str) -> dict[str, Any]:
        profile_id = resolve_inference_profile(requested_model_id)
        started = time.perf_counter()
        local_output = run_agent(scenario["input"], plane=PLANE_EVAL)
        draft = converse_text(
            model_id=profile_id,
            system=converse_system_with_cache_point(agent_cacheable_prefix()),
            user=_draft_user_prompt(scenario, local_output),
            max_tokens=400,
            temperature=0.0,
            client=self._client,
            prompt_cache=True,
        )
        wall_time_ms = round((time.perf_counter() - started) * 1000, 3)
        draft_text = draft["text"]
        notes = list(local_output.get("notes") or []) + [f"bedrock_draft:{profile_id}"]
        if not draft_text:
            notes.append("bedrock_draft_empty")
        output = {
            **local_output,
            # Keep empty draft visible; do not silently credit the local stub answer.
            "answer": draft_text,
            "model_id": profile_id,
            "notes": notes,
        }
        usage = draft["usage"]
        return {
            "requested_model_id": requested_model_id,
            "candidate_executed": True,
            "actual_model_id": profile_id,
            "execution_mode": self.execution_mode,
            "wall_time_ms": wall_time_ms,
            "usage": usage,
            "cost_usd": estimate_cost_usd(profile_id, usage),
            "output": output,
        }


class BedrockHaikuJudge:
    """LLM-as-judge using Claude Haiku 4.5 and the versioned rubric."""

    def __init__(
        self,
        *,
        judge_model_id: str = DEFAULT_JUDGE_MODEL_ID,
        rubric_path: Path = DEFAULT_RUBRIC_PATH,
        client: Any | None = None,
    ) -> None:
        self.judge_model_id = judge_model_id
        self._client = client
        self._rubric_path = rubric_path
        self._rubric = json.loads(rubric_path.read_text(encoding="utf-8"))
        version = self._rubric.get("judge_version")
        if not isinstance(version, str) or not version:
            raise ValueError("judge rubric requires judge_version")
        self.judge_version = version
        self._cache_prefix = judge_cacheable_prefix(rubric_path)

    def evaluate(
        self,
        scenario: dict[str, Any],
        model_output: dict[str, Any],
    ) -> dict[str, Any]:
        threshold = self._rubric["pass_thresholds"].get(scenario["task_type"], 4)
        user = json.dumps(
            {
                "scenario": {
                    "id": scenario["id"],
                    "task_type": scenario["task_type"],
                    "input": scenario["input"],
                    "expected_outcome": scenario["expected_outcome"],
                    "expected_answer_facts": scenario.get("expected_answer_facts") or [],
                    "expected_citations": scenario.get("expected_citations") or [],
                },
                "candidate_output": {
                    "answer": model_output.get("answer"),
                    "status": model_output.get("status"),
                    "citations": model_output.get("citations") or [],
                    "tool_calls": model_output.get("tool_calls") or [],
                },
                "dimensions": self._rubric["dimensions"],
                "pass_threshold": threshold,
                "response_schema": {
                    "faithfulness": "int 1-5",
                    "helpfulness": "int 1-5",
                    "policy_adherence": "int 1-5",
                    "reason": "short string",
                },
            },
            indent=2,
        )
        raw: dict[str, Any] | None = None
        try:
            raw = converse_text(
                model_id=self.judge_model_id,
                system=converse_system_with_cache_point(self._cache_prefix),
                user=user,
                max_tokens=300,
                temperature=0.0,
                client=self._client,
                prompt_cache=True,
            )
            scores = extract_json_object(raw["text"])
            faithfulness = int(scores["faithfulness"])
            helpfulness = int(scores["helpfulness"])
            policy_adherence = int(scores["policy_adherence"])
            for value in (faithfulness, helpfulness, policy_adherence):
                if value < 1 or value > 5:
                    raise ValueError("scores must be integers from 1 to 5")
            passed = min(faithfulness, helpfulness, policy_adherence) >= int(threshold)
            return {
                "status": "completed",
                "judge_version": self.judge_version,
                "model_id": self.judge_model_id,
                "scores": {
                    "faithfulness": faithfulness,
                    "helpfulness": helpfulness,
                    "policy_adherence": policy_adherence,
                },
                "pass": passed,
                "reason": str(scores.get("reason") or ""),
                "usage": raw["usage"],
                "cost_usd": estimate_cost_usd(self.judge_model_id, raw["usage"]),
            }
        except Exception as exc:  # noqa: BLE001 — fail closed, never fabricate scores
            failed: dict[str, Any] = {
                "status": "error",
                "judge_version": self.judge_version,
                "model_id": self.judge_model_id,
                "scores": {
                    "faithfulness": None,
                    "helpfulness": None,
                    "policy_adherence": None,
                },
                "pass": None,
                "reason": f"Judge failed closed: {type(exc).__name__}: {exc}",
            }
            # Preserve token spend when Converse succeeded but parsing/scoring failed.
            if raw is not None:
                failed["usage"] = raw["usage"]
                failed["cost_usd"] = estimate_cost_usd(self.judge_model_id, raw["usage"])
            return failed
