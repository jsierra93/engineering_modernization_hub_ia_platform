#!/usr/bin/env bash

# Runs one demo scenario end to end against the deployed API (create, approve, wait, report).
#   ./scripts/run-scenario.sh exitoso|inviable|inyeccion|prueba_fallida [--no-approve] [--reject] [--max-usd N] [--max-minutes N]
# Each run spends Bedrock budget.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${REPO_ROOT}/.venv/Scripts/python.exe"
[[ -x "${PY}" ]] || PY="${REPO_ROOT}/.venv/bin/python"
[[ -x "${PY}" ]] || PY="python3"

export AWS_PROFILE="${AWS_PROFILE:-personal}"
exec "${PY}" "${REPO_ROOT}/scripts/run_scenario.py" "$@"
