#!/usr/bin/env bash
# scripts/run_local.sh
#
# Brings up the Fase 1 slice of the Engineering Modernization Hub entirely
# locally, against Floci (https://floci.io) -- never against real AWS -- and
# smoke-tests the deployed API. Optionally also starts Backstage.
#
# What this does, in order:
#   1. Ensures Floci is running and healthy (starts it via Docker if not).
#   2. Rebuilds the real `services/api` Lambda package (Python 3.14, x86_64
#      -- not the arm64 used for real AWS; Floci doesn't cross-emulate).
#   3. `terraform apply`s infrastructure/envs/local -- whose provider is
#      hard-validated (see envs/local/variables.tf) to only ever point at
#      localhost/127.0.0.1. This step may prompt for permission the first
#      time you run it interactively -- that's expected and correct; approve
#      it once you've confirmed you're pointed at Floci, never blind.
#   4. POSTs a real run to the deployed API, then GETs it back.
#   5. With --with-backstage: also starts the Backstage instance (guest
#      login only -- the modhub/modhub-backend plugins aren't built yet,
#      see PLAN.md Fase 5, so Backstage can't call the API through the UI
#      for anything meaningful today).
#
# Usage:
#   scripts/run_local.sh                  # infra + API smoke test only
#   scripts/run_local.sh --with-backstage # also start Backstage
#   scripts/run_local.sh --teardown       # terraform destroy against Floci + stop containers
#
# Requires: docker, terraform, curl, python3. Nothing here ever needs real
# AWS credentials -- Floci accepts the dummy test/test creds baked into
# infrastructure/envs/local.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

FLOCI_URL="http://localhost:4566"
FLOCI_HEALTH_URL="${FLOCI_URL}/_localstack/health"
TF="${TERRAFORM_BIN:-terraform}"
ENV_DIR="infrastructure/envs/local"

step() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--teardown" ]]; then
  step "Tearing down: terraform destroy against Floci"
  if [[ -d "${ENV_DIR}/.terraform" ]]; then
    (cd "${ENV_DIR}" && "${TF}" destroy -auto-approve) || echo "  (destroy failed or nothing to destroy -- continuing)"
  fi
  step "Stopping containers"
  docker rm -f floci >/dev/null 2>&1 && echo "  floci stopped" || echo "  floci was not running"
  if [[ -f apps/backstage/docker-compose.yml ]]; then
    (cd apps/backstage && docker compose down) || true
  fi
  echo "Done."
  exit 0
fi

require_cmd docker
require_cmd curl
require_cmd python3
require_cmd "${TF}"

# 1. Floci ---------------------------------------------------------------
step "Checking Floci at ${FLOCI_URL}"
if ! curl -fsS "${FLOCI_HEALTH_URL}" >/dev/null 2>&1; then
  echo "  Not responding -- starting via Docker"
  docker rm -f floci >/dev/null 2>&1 || true
  docker run -d --name floci -p 4566:4566 floci/floci:latest >/dev/null
  echo -n "  Waiting for healthy status"
  for _ in $(seq 1 30); do
    if curl -fsS "${FLOCI_HEALTH_URL}" >/dev/null 2>&1; then break; fi
    echo -n "."
    sleep 1
  done
  echo
fi
curl -fsS "${FLOCI_HEALTH_URL}" >/dev/null 2>&1 || die "Floci did not come up healthy -- check 'docker logs floci'"
echo "  Floci is healthy."

# 2. Build the real Lambda package ----------------------------------------
# x86_64, not the arm64 used for real AWS (infrastructure/envs/personal):
# Floci runs Lambda containers as the Docker host's native architecture and
# does not cross-emulate arm64 -- confirmed empirically, see
# infrastructure/envs/local/main.tf's lambda_architectures override.
step "Building services/api Lambda package (Python 3.14, x86_64 -- Floci does not cross-emulate arm64)"
bash infrastructure/scripts/build_lambda.sh "${REPO_ROOT}/infrastructure/scripts/build/api_lambda_real.zip" x86_64

# 3. Terraform apply -- Floci only ----------------------------------------
step "terraform apply (infrastructure/envs/local -- Floci only, validated by variable regex)"
(
  cd "${ENV_DIR}"
  "${TF}" init -input=false
  "${TF}" apply -auto-approve
)
AWS_SHAPED_ENDPOINT="$(cd "${ENV_DIR}" && "${TF}" output -raw api_endpoint)"
[[ -n "${AWS_SHAPED_ENDPOINT}" ]] || die "terraform did not produce an api_endpoint output"
# Floci returns the same URL shape real AWS would (https://<id>.execute-api...),
# which doesn't resolve to anything local. The actual way to reach it is
# LocalStack/Floci's own local routing convention -- confirmed empirically,
# not assumed:
API_ID="$(echo "${AWS_SHAPED_ENDPOINT}" | sed -E 's#https://([^.]+)\..*#\1#')"
API_ENDPOINT="http://localhost:4566/_aws/execute-api/${API_ID}/\$default"
echo "  Real (unreachable) AWS-shaped endpoint from terraform output, for reference only."
echo "  Actual local endpoint: ${API_ENDPOINT}"

# 4. Smoke test ------------------------------------------------------------
step "Smoke test: POST ${API_ENDPOINT}/modhub/v1/runs"
SMOKE_COMMIT="$(python3 -c "import hashlib; print(hashlib.sha1(b'engineering-modernization-hub-smoke-test').hexdigest())")"
RUN_BODY=$(cat <<EOF
{
  "repo": "octocat/Hello-World",
  "commit": "${SMOKE_COMMIT}",
  "objetivo": "smoke test local via scripts/run_local.sh",
  "max_usd": 1,
  "max_iterations": 1,
  "max_minutes": 5
}
EOF
)
RUN_RESPONSE="$(curl -fsS -X POST "${API_ENDPOINT}/modhub/v1/runs" \
  -H "Content-Type: application/json" \
  -H "X-Requested-By: local-smoke-test" \
  -d "${RUN_BODY}")" || die "POST /runs failed -- see curl output above"
echo "${RUN_RESPONSE}" | python3 -m json.tool
RUN_ID="$(echo "${RUN_RESPONSE}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])')" \
  || die "response did not contain a run_id -- got: ${RUN_RESPONSE}"

step "Smoke test: GET ${API_ENDPOINT}/modhub/v1/runs/${RUN_ID}"
curl -fsS "${API_ENDPOINT}/modhub/v1/runs/${RUN_ID}" | python3 -m json.tool

# 5. Optional Backstage -----------------------------------------------------
if [[ "${1:-}" == "--with-backstage" ]]; then
  step "Starting Backstage (docker compose, guest login only)"
  (cd apps/backstage && docker compose up -d)
  echo "  Backstage: http://localhost:7007 (guest login -- modhub plugins not built yet, PLAN.md Fase 5)"
fi

step "Done."
cat <<EOF
  API endpoint:   ${API_ENDPOINT}
  Floci health:   ${FLOCI_HEALTH_URL}
  Run created:    ${RUN_ID}
  Teardown with:  scripts/run_local.sh --teardown
EOF
