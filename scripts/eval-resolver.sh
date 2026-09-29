#!/usr/bin/env bash

# Scores Bedrock models on the objective-to-strategy resolver (real prompt, fixed cases in scripts/resolver_cases.json).
#   ./scripts/eval-resolver.sh                          the model configured in Terraform (resolver_model_id)
#   ./scripts/eval-resolver.sh us.amazon.nova-lite-v1:0 [MODEL ...] [--rate MODEL=IN,OUT] [--min-accuracy 0.9]
# Run it before changing resolver_model_id. Each model costs about 14 short Bedrock calls (cents).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${REPO_ROOT}/.venv/Scripts/python.exe"
[[ -x "${PY}" ]] || PY="${REPO_ROOT}/.venv/bin/python"
[[ -x "${PY}" ]] || PY="python3"

export AWS_PROFILE="${AWS_PROFILE:-personal}"

if [[ $# -eq 0 || "${1}" == --* ]]; then
  CONFIGURED="$(cd "${REPO_ROOT}/infrastructure/envs" && echo 'var.resolver_model_id' | terraform console -no-color | tr -d '"')"
  set -- "${CONFIGURED}" "$@"
fi

exec "${PY}" "${REPO_ROOT}/scripts/eval_resolver.py" "$@"
