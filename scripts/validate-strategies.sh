#!/usr/bin/env bash

# Validates every strategy package before it is deployed: manifest rules, unique ids and
# that each declared check exists in the sandbox. Run it after adding or editing a strategy.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${REPO_ROOT}/.venv/Scripts/python.exe"
[[ -x "${PY}" ]] || PY="${REPO_ROOT}/.venv/bin/python"
[[ -x "${PY}" ]] || PY="python3"

exec "${PY}" -m strategies_sdk.validate "${REPO_ROOT}"
