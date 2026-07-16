# Destroy all SupportRouter CDK stacks (ADR-008 dormancy).
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "infra")

Write-Host "SupportRouter teardown — using current AWS credentials / region"

if (-not $Force) {
    $ans = Read-Host "Destroy ALL SupportRouter stacks? [y/N]"
    if ($ans -notmatch '^(y|yes)$') {
        Write-Host "Aborted."
        exit 1
    }
}

npx cdk destroy --all --force
Write-Host "Teardown requested. Run post-teardown checklist in docs/03_operations/RUNBOOK.md"
