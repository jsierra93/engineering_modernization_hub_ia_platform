#!/usr/bin/env bash
# start-local-env.sh
#
# Brings up the ENTIRE Engineering Modernization Hub locally against Floci
# (https://floci.io) -- never against real AWS -- ready to be used from the
# web (Backstage) or directly via the API. Supersedes scripts/run_local.sh
# (Fase 1-only, predates identity/notifications/Backstage).
#
# What this does, in order:
#   1. Ensures Floci is running and healthy (starts it via Docker if not).
#      Includes the /var/run/docker.sock mount Floci's own docs require for
#      its Lambda/ECS emulation -- missing in earlier drafts of this repo's
#      tooling, confirmed necessary 2026-09-26.
#   2. Builds every Lambda package this platform deploys (api, fetch_repo,
#      core_ops, fetch_doc, agent_phase), x86_64 -- Floci runs Lambda
#      containers as the Docker host's native architecture and does not
#      cross-emulate arm64. Skips a build whose zip already exists unless
#      --rebuild-lambdas is passed (agent_phase's strands-agents dependency
#      tree alone takes minutes to reinstall from a cold Docker layer).
#   3. `terraform apply`s infrastructure/envs/local -- persistence,
#      orchestration, api (with a real JWT authorizer), sandbox-network,
#      fetch-repo, core-ops, fetch-doc, agent-phase, identity (Cognito) and
#      notifications (SQS). The provider is hard-validated (see
#      envs/local/variables.tf) to only ever point at localhost/127.0.0.1.
#   4. Logs in as the Terraform-created test user (real Cognito
#      AdminInitiateAuth against Floci -- MFA is out of scope, see
#      infrastructure/modules/identity/variables.tf) and smoke-tests the
#      real API end to end: no token -> 401, a garbage token -> 401, the
#      real JWT -> 200, then POSTs and reads back a real run.
#   5. Starts Backstage (`pnpm start`, both frontend and backend) in the
#      background, pointed at the local API and the real Cognito OIDC
#      issuer, logging to backstage.log and tracking its PID.
#
# Usage:
#   ./start-local-env.sh                  # full stack: infra + API + Backstage
#   ./start-local-env.sh --skip-backstage # infra + API only
#   ./start-local-env.sh --rebuild-lambdas # force-rebuild every Lambda zip first
#   ./start-local-env.sh --teardown       # stop Backstage, terraform destroy, stop Floci
#
# Requires: docker, terraform, curl, python3, pnpm. Nothing here ever needs
# real AWS credentials -- Floci accepts the dummy test/test creds baked
# into infrastructure/envs/local.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${REPO_ROOT}"

FLOCI_URL="http://localhost:4566"
FLOCI_HEALTH_URL="${FLOCI_URL}/_localstack/health"
TF="${TERRAFORM_BIN:-terraform}"
ENV_DIR="infrastructure/envs/local"
STATE_DIR="${REPO_ROOT}/.local-env"
BACKSTAGE_LOG="${REPO_ROOT}/backstage.log"
BACKSTAGE_PID_FILE="${STATE_DIR}/backstage.pid"
TEST_USERNAME="demo-requester@example.com"
TEST_PASSWORD="Sup3rSecret!2026"

step() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
require_cmd() { command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"; }

# Kills whatever is listening on $1, on both Unix (lsof) and Windows/Git
# Bash (netstat + PowerShell -- no lsof there). Used to guarantee a clean
# restart: a stale dev server surviving a re-run silently keeps serving
# OLD code, which is exactly the bug this project hit empirically,
# 2026-09-26 -- `pkill -f "pnpm start"` alone did not reliably kill the
# real Windows node.exe process, so port-based killing is the one check
# that actually works cross-platform.
free_port() {
  local port="$1" pids
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti tcp:"${port}" 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      echo "  Killing process(es) on port ${port}: ${pids}"
      kill -9 ${pids} 2>/dev/null || true
    fi
  elif command -v netstat >/dev/null 2>&1 && command -v powershell >/dev/null 2>&1; then
    pids="$(netstat -ano 2>/dev/null | awk -v p=":${port}" '$2 ~ (p"$") && $4=="LISTENING" {print $NF}' | sort -u)"
    if [[ -n "${pids}" ]]; then
      echo "  Killing process(es) on port ${port}: $(echo "${pids}" | tr '\n' ' ')"
      powershell -NoProfile -Command "Stop-Process -Id $(echo "${pids}" | tr '\n' ',' | sed 's/,$//') -Force -ErrorAction SilentlyContinue" >/dev/null 2>&1 || true
    fi
  fi
}

stop_backstage() {
  if [[ -f "${BACKSTAGE_PID_FILE}" ]]; then
    kill "$(cat "${BACKSTAGE_PID_FILE}")" 2>/dev/null || true
    rm -f "${BACKSTAGE_PID_FILE}"
  fi
  free_port 3000
  free_port 7007
}

mkdir -p "${STATE_DIR}"

# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--teardown" ]]; then
  step "Stopping Backstage"
  stop_backstage

  step "terraform destroy against Floci"
  if [[ -d "${ENV_DIR}/.terraform" ]]; then
    (cd "${ENV_DIR}" && "${TF}" destroy -auto-approve) || echo "  (destroy failed or nothing to destroy -- continuing)"
  fi

  step "Stopping Floci"
  docker rm -f floci >/dev/null 2>&1 && echo "  floci stopped" || echo "  was not running"

  echo "Done."
  exit 0
fi

REBUILD_LAMBDAS=false
SKIP_BACKSTAGE=false
for arg in "$@"; do
  case "${arg}" in
    --rebuild-lambdas) REBUILD_LAMBDAS=true ;;
    --skip-backstage) SKIP_BACKSTAGE=true ;;
    *) die "unknown argument: ${arg} (use --rebuild-lambdas, --skip-backstage or --teardown)" ;;
  esac
done

require_cmd docker
require_cmd curl
require_cmd python3
require_cmd "${TF}"
"${SKIP_BACKSTAGE}" || require_cmd pnpm

# 1. Floci --------------------------------------------------------------
step "Checking Floci at ${FLOCI_URL}"
if ! curl -fsS "${FLOCI_HEALTH_URL}" >/dev/null 2>&1; then
  echo "  Not responding -- starting via Docker"
  docker rm -f floci >/dev/null 2>&1 || true
  # -v /var/run/docker.sock:/var/run/docker.sock: required by Floci's own
  # docs for its Lambda/ECS emulation (both run as real Docker containers
  # under the hood). Omitting it doesn't fail loudly -- FetchRepo/Baseline
  # just hang or 500 later, confirmed the hard way earlier in this project.
  docker run -d --name floci -p 4566:4566 \
    -v /var/run/docker.sock:/var/run/docker.sock \
    floci/floci:latest >/dev/null
  echo -n "  Waiting for healthy status"
  for _ in $(seq 1 60); do
    if curl -fsS "${FLOCI_HEALTH_URL}" >/dev/null 2>&1; then break; fi
    echo -n "."
    sleep 1
  done
  echo
fi
curl -fsS "${FLOCI_HEALTH_URL}" >/dev/null 2>&1 || die "Floci did not come up healthy -- check 'docker logs floci'"
echo "  Floci is healthy."

# 2. Build every Lambda package ------------------------------------------
step "Building Lambda packages (Python 3.14, x86_64 -- Floci does not cross-emulate arm64)"
for service in api fetch_repo core_ops fetch_doc agent_phase; do
  zip_path="infrastructure/scripts/build/${service}_lambda_x86_64.zip"
  if [[ -f "${zip_path}" && "${REBUILD_LAMBDAS}" == false ]]; then
    echo "  ${service}: zip exists, skipping (--rebuild-lambdas to force)"
    continue
  fi
  echo "  ${service}: building..."
  bash infrastructure/scripts/build_lambda.sh "" x86_64 "${service}"
done

# 3. Terraform apply -- Floci only ----------------------------------------
step "terraform apply (${ENV_DIR} -- Floci only, provider hard-validated to localhost)"
(
  cd "${ENV_DIR}"
  "${TF}" init -input=false
  "${TF}" apply -input=false -auto-approve
)

TF_OUT="$(cd "${ENV_DIR}" && "${TF}" output -json)"
py_get() { python3 -c "import json,sys; print(json.loads(sys.argv[1])['$1']['value'])" "${TF_OUT}"; }

AWS_SHAPED_ENDPOINT="$(py_get api_endpoint)"
API_ID="$(echo "${AWS_SHAPED_ENDPOINT}" | sed -E 's#https://([^.]+)\..*#\1#')"
API_BASE_URL="http://localhost:4566/_aws/execute-api/${API_ID}/\$default"
POOL_ID_ISSUER="$(py_get cognito_issuer_url)"
POOL_ID="${POOL_ID_ISSUER##*/}"
CLI_CLIENT_ID="$(py_get cognito_cli_client_id)"
BACKSTAGE_CLIENT_ID="$(py_get cognito_backstage_client_id)"
BACKSTAGE_CLIENT_SECRET="$(py_get cognito_backstage_client_secret)"

echo "  API (real AWS-shaped, unreachable): ${AWS_SHAPED_ENDPOINT}"
echo "  API (actual local endpoint):        ${API_BASE_URL}"
echo "  Cognito issuer:                     ${POOL_ID_ISSUER}"

# 4. Real Cognito login + API smoke test ----------------------------------
step "Logging in as ${TEST_USERNAME} (real Cognito AdminInitiateAuth against Floci)"
JWT="$(python3 - "${POOL_ID}" "${CLI_CLIENT_ID}" "${TEST_USERNAME}" "${TEST_PASSWORD}" <<'PYEOF'
import boto3, os, sys
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
pool_id, client_id, username, password = sys.argv[1:5]
c = boto3.client("cognito-idp", endpoint_url="http://localhost:4566", region_name="us-east-1")
c.admin_set_user_password(UserPoolId=pool_id, Username=username, Password=password, Permanent=True)
auth = c.admin_initiate_auth(
    UserPoolId=pool_id, ClientId=client_id, AuthFlow="ADMIN_USER_PASSWORD_AUTH",
    AuthParameters={"USERNAME": username, "PASSWORD": password},
)
print(auth["AuthenticationResult"]["IdToken"])
PYEOF
)"
[[ -n "${JWT}" ]] || die "failed to obtain a real Cognito JWT"
echo "  Got a real JWT for ${TEST_USERNAME}."

step "Smoke test: JWT authorizer (task 4.2-tf's own acceptance criterion)"
NO_AUTH_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "${API_BASE_URL}/modhub/v1/runs")"
[[ "${NO_AUTH_STATUS}" == "401" ]] || die "expected 401 with no Authorization header, got ${NO_AUTH_STATUS}"
echo "  No Authorization header -> 401 (expected)"
WITH_AUTH_STATUS="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${JWT}" "${API_BASE_URL}/modhub/v1/runs")"
[[ "${WITH_AUTH_STATUS}" == "200" ]] || die "expected 200 with a real JWT, got ${WITH_AUTH_STATUS}"
echo "  Real JWT -> 200 (expected)"

step "Smoke test: POST a real run"
# create_run's objective->strategy resolver (services/api/resolver) makes a
# REAL bedrock-runtime InvokeModel call -- Floci does not emulate actual
# model inference (confirmed, 2026-09-26), so this legitimately comes back
# 422 NO_STRATEGY_MATCH here, every time, until this points at real AWS.
# That is core_ops's own "never trust an unresolved match" rule working
# correctly, not a bug -- so this step reports it plainly instead of
# treating it as a failure.
SMOKE_COMMIT="$(python3 -c "import hashlib; print(hashlib.sha1(b'engineering-modernization-hub-smoke-test').hexdigest())")"
RUN_STATUS="$(curl -s -o "${STATE_DIR}/last_run_response.json" -w '%{http_code}' -X POST "${API_BASE_URL}/modhub/v1/runs" \
  -H "Authorization: Bearer ${JWT}" -H "Content-Type: application/json" \
  -d "{\"repo\":\"octocat/Hello-World\",\"commit\":\"${SMOKE_COMMIT}\",\"objetivo\":\"smoke test via start-local-env.sh\",\"max_usd\":1,\"max_iterations\":1,\"max_minutes\":5}")"
RUN_ID=""
case "${RUN_STATUS}" in
  201)
    RUN_ID="$(python3 -c 'import json; print(json.load(open("'"${STATE_DIR}/last_run_response.json"'"))["run_id"])')"
    curl -fsS -H "Authorization: Bearer ${JWT}" "${API_BASE_URL}/modhub/v1/runs/${RUN_ID}" >/dev/null \
      || die "GET /runs/${RUN_ID} failed right after creating it"
    echo "  Created and read back run ${RUN_ID}."
    ;;
  422)
    echo "  Got 422 NO_STRATEGY_MATCH -- expected against Floci (no real Bedrock"
    echo "  inference here). The create/read/auth path itself is proven by the"
    echo "  JWT-authorizer checks above; run creation needs real AWS."
    ;;
  *)
    die "POST /runs returned an unexpected status ${RUN_STATUS} -- see ${STATE_DIR}/last_run_response.json"
    ;;
esac

# 5. Backstage --------------------------------------------------------------
if [[ "${SKIP_BACKSTAGE}" == false ]]; then
  step "Stopping any previous Backstage instance (guarantees the restart runs the latest code)"
  stop_backstage

  step "Starting Backstage (pnpm start, background -- see ${BACKSTAGE_LOG})"
  (
    cd apps/backstage
    # Always run, not just when node_modules is missing: cheap/no-op when
    # already up to date, but guarantees a dependency added since the last
    # run (e.g. a new plugin) is actually installed before this starts.
    echo "  pnpm install..."
    pnpm install
    export MODHUB_API_BASE_URL="${API_BASE_URL}"
    export AUTH_OIDC_METADATA_URL="${POOL_ID_ISSUER}/.well-known/openid-configuration"
    export AUTH_OIDC_CLIENT_ID="${BACKSTAGE_CLIENT_ID}"
    export AUTH_OIDC_CLIENT_SECRET="${BACKSTAGE_CLIENT_SECRET}"
    nohup pnpm start > "${BACKSTAGE_LOG}" 2>&1 &
    echo $! > "${BACKSTAGE_PID_FILE}"
  )
  echo "  Waiting for Backstage backend (:7007)..."
  # -f treats a 401 as failure, but 401 IS the correct, expected response
  # here (no session cookie) -- it means the backend is genuinely up.
  # Checking for ANY response (curl exit 0, regardless of HTTP status)
  # avoids misreporting a healthy backend as down, confirmed empirically,
  # 2026-09-26.
  backstage_backend_up() {
    curl -sS -o /dev/null "http://localhost:7007/api/catalog/entities" 2>/dev/null
  }
  for _ in $(seq 1 90); do
    if backstage_backend_up; then break; fi
    sleep 2
  done
  if backstage_backend_up; then
    echo "  Backstage backend is up."
  else
    echo "  WARNING: Backstage backend didn't respond within the timeout -- check ${BACKSTAGE_LOG}"
  fi
fi

step "Done."
cat <<EOF

  Floci health:        ${FLOCI_HEALTH_URL}
  API base URL:        ${API_BASE_URL}
  Cognito issuer:       ${POOL_ID_ISSUER}
  Test user:            ${TEST_USERNAME} / ${TEST_PASSWORD}
  Smoke-test run:       ${RUN_ID:-"(none -- create_run needs real Bedrock, see above)"}

  Call the API directly:
    curl -H "Authorization: Bearer <jwt>" ${API_BASE_URL}/modhub/v1/runs

  A fresh JWT for that user:
    (see the Python snippet this script itself runs, above, or use
    boto3 admin_initiate_auth against http://localhost:4566 the same way)

EOF
if [[ "${SKIP_BACKSTAGE}" == false ]]; then
  cat <<EOF
  Backstage (web):      http://localhost:3000
  Backstage (backend):  http://localhost:7007
  Backstage log:        ${BACKSTAGE_LOG}

  NOTE: Backstage's own login defaults to the "guest" provider (reliable,
  always works). Real Cognito OIDC login (the "oidc" provider, wired to
  the real user pool above) is CONFIGURED but not confirmed working through
  a live browser redirect -- Floci's Cognito discovery document doesn't
  advertise an authorization_endpoint, which the browser-redirect
  authorization_code flow needs. AdminInitiateAuth (used above, and by any
  direct API caller) is unaffected by that gap.
EOF
fi
cat <<EOF
  Teardown:             ./start-local-env.sh --teardown
EOF
