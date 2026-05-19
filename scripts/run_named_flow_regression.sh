#!/usr/bin/env bash
# Run named simulator flows under api_only policy and emit a reliability summary.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export SIM_FAILURE_POLICY="${SIM_FAILURE_POLICY:-api_only}"
export SIM_PREFLIGHT_STRATEGY="${SIM_PREFLIGHT_STRATEGY:-auto_recover}"

exec python3 scripts/run_named_flow_regression.py "$@"
