"""AgentCore Runtime HTTP entrypoint wrapping SupportRouter (ADR-024).

Deployed via ``AgentRuntimeArtifact.from_code_asset``; local import requires
``bedrock-agentcore``.
"""

from __future__ import annotations

from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from supportrouter.agentcore_adapter import handle_agentcore_payload

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AgentCore ``/invocations`` handler."""
    del context
    return handle_agentcore_payload(payload if isinstance(payload, dict) else {})


if __name__ == "__main__":
    app.run()
