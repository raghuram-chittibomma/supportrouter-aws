#!/usr/bin/env bash
# Destroy all SupportRouter CDK stacks (ADR-008 dormancy).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/infra"

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

echo "SupportRouter teardown — region context from cdk.json / AWS_REGION"
if [[ "$FORCE" -ne 1 ]]; then
  read -r -p "Destroy ALL SupportRouter stacks? [y/N] " ans
  case "$ans" in
    y|Y|yes|YES) ;;
    *) echo "Aborted."; exit 1 ;;
  esac
fi

npx cdk destroy --all --force
echo "Teardown requested. Run post-teardown checklist in docs/03_operations/RUNBOOK.md"
