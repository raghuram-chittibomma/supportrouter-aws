# ADR-015: Reproducible Chat Lambda Runtime Bundle

## Status

Accepted

## Context

The HTTP chat Lambda originally packaged only `src/`. It could not import
`langgraph`, and local order tools could not read the synthetic fixtures under
`data/`. Docker is not available in every developer environment, while several
Python dependencies contain architecture-specific native wheels.

## Decision

Build one ARM64 Python 3.12 Lambda ZIP during CDK asset staging:

- pin the complete transitive runtime dependency set in
  `infra/chat_runtime_requirements.txt`
- install Linux ARM64 CPython 3.12 wheels with local `pip` bundling
- retain an equivalent Lambda-runtime Docker command as a CI fallback
- preserve `src/supportrouter` and set `PYTHONPATH=/var/task/src`
- copy only `data/sample` and `data/knowledge_base`
- exclude the Gradio UI, bytecode, tests, docs, and other repository content
- hash the bundled output rather than the repository input

The deployed graph remains the local-stub runtime in this slice. Its role keeps
logs-only permissions; managed Bedrock, DynamoDB, and Lambda-tool invocation
permissions are not added.

## Consequences

- `POST /chat` can cold-start without an external layer or container registry.
- Local CDK synthesis requires network access to resolve pinned wheels on the
  first build; pip caching reduces later builds.
- If local wheel installation fails or is explicitly disabled, CDK uses the
  equivalent Linux ARM64 Docker bundler.
- Dependency updates are explicit and require rebuilding and smoke-testing the
  Lambda asset.
- The packaged synthetic fixture paths match the existing local tool/retrieval
  contracts.
- This resolves the packaging deferral recorded in ADR-014. Bedrock drafting,
  managed guardrail invocation, and remote Lambda-tool adapters remain separate
  slices.
