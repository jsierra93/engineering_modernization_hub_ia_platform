#!/usr/bin/env bash
#
# Starts Backstage against either environment:
#
#   ./start-backstage.sh local      -> Floci (needs start-local-env.sh running first)
#   ./start-backstage.sh personal   -> real AWS (needs AWS_PROFILE credentials)
#
# Reads the target env's Terraform outputs, mints a real Cognito token for
# the demo user, and starts Backstage pointed at that API.

set -euo pipefail

TARGET="${1:-}"
TF="${TERRAFORM_BIN:-terraform}"
TEST_USERNAME="${MODHUB_TEST_USERNAME:-demo-requester@example.com}"
TEST_PASSWORD="${MODHUB_TEST_PASSWORD:-Sup3rSecret!2026}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

die() { echo "error: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }

case "${TARGET}" in
  local)
    ENV_DIR="infrastructure/envs/local"
    COGNITO_ENDPOINT="http://localhost:4566"
    COGNITO_REGION="us-east-1"
    export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
    export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
    ;;
  personal)
    ENV_DIR="infrastructure/envs/personal"
    COGNITO_ENDPOINT=""
    COGNITO_REGION="us-east-2"
    export AWS_PROFILE="${AWS_PROFILE:-personal}"
    ;;
  "")
    die "no target given -- use '$(basename "$0") local' or '$(basename "$0") personal'"
    ;;
  *)
    die "unknown target '${TARGET}' -- use 'local' or 'personal'"
    ;;
esac

echo
echo "########## TARGET: ${TARGET} ##########"

cd "${REPO_ROOT}"

step "Reading Terraform outputs (${ENV_DIR})"
TF_OUT="$(cd "${ENV_DIR}" && "${TF}" output -json)" || die "terraform output failed -- has this env been applied?"
py_get() { python3 -c "import json,sys; print(json.loads(sys.argv[1])['$1']['value'])" "${TF_OUT}"; }

AWS_SHAPED_ENDPOINT="$(py_get api_endpoint)"
if [[ "${TARGET}" == "local" ]]; then
  # Floci serves API Gateway under a path, not the AWS-shaped hostname.
  API_ID="$(echo "${AWS_SHAPED_ENDPOINT}" | sed -E 's#https://([^.]+)\..*#\1#')"
  API_BASE_URL="http://localhost:4566/_aws/execute-api/${API_ID}/\$default"
else
  API_BASE_URL="${AWS_SHAPED_ENDPOINT%/}"
fi

POOL_ID_ISSUER="$(py_get cognito_issuer_url)"
POOL_ID="${POOL_ID_ISSUER##*/}"
CLI_CLIENT_ID="$(py_get cognito_cli_client_id)"
BACKSTAGE_CLIENT_ID="$(py_get cognito_backstage_client_id)"
BACKSTAGE_CLIENT_SECRET="$(py_get cognito_backstage_client_secret)"
NOTIFICATIONS_QUEUE_URL="$(py_get notifications_queue_url)"

echo "  API:            ${API_BASE_URL}"
echo "  Cognito issuer: ${POOL_ID_ISSUER}"

step "Minting a Cognito token for ${TEST_USERNAME} (smoke test)"
JWT="$(python3 - "${POOL_ID}" "${CLI_CLIENT_ID}" "${TEST_USERNAME}" "${TEST_PASSWORD}" "${COGNITO_ENDPOINT}" "${COGNITO_REGION}" <<'PYEOF'
import boto3, sys
pool_id, client_id, username, password, endpoint, region = sys.argv[1:7]
kwargs = {"region_name": region}
if endpoint:
    kwargs["endpoint_url"] = endpoint
c = boto3.client("cognito-idp", **kwargs)
# Terraform creates the user in FORCE_CHANGE_PASSWORD; make it usable.
c.admin_set_user_password(UserPoolId=pool_id, Username=username, Password=password, Permanent=True)
# USER_PASSWORD_AUTH, not the admin flow: the cli client is public and only
# enables the non-admin flows a real CLI user would have.
auth = c.initiate_auth(
    ClientId=client_id, AuthFlow="USER_PASSWORD_AUTH",
    AuthParameters={"USERNAME": username, "PASSWORD": password},
)
print(auth["AuthenticationResult"]["IdToken"])
PYEOF
)"
[[ -n "${JWT}" ]] || die "failed to obtain a Cognito JWT"
echo "  Token obtained (valid ~60 min)."

step "Smoke test: JWT authorizer"
NO_AUTH="$(curl -s -o /dev/null -w '%{http_code}' "${API_BASE_URL}/modhub/v1/runs" || true)"
WITH_AUTH="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${JWT}" "${API_BASE_URL}/modhub/v1/runs" || true)"
echo "  no token -> ${NO_AUTH} (expect 401)"
echo "  token    -> ${WITH_AUTH} (expect 200)"

step "Stopping any previous Backstage instance"
for PORT in 3000 7007; do
  PIDS="$(netstat -ano 2>/dev/null | awk -v p=":${PORT}" '$2 ~ (p"$") && $4=="LISTENING" {print $NF}' | sort -u || true)"
  if [[ -n "${PIDS}" ]]; then
    echo "  port ${PORT}: killing $(echo "${PIDS}" | tr '\n' ' ')"
    for PID in ${PIDS}; do
      powershell -NoProfile -Command "Stop-Process -Id ${PID} -Force -ErrorAction SilentlyContinue" >/dev/null 2>&1 || true
    done
  fi
done

step "Starting Backstage against '${TARGET}'"
export MODHUB_API_BASE_URL="${API_BASE_URL}"
export MODHUB_NOTIFICATIONS_QUEUE_URL="${NOTIFICATIONS_QUEUE_URL}"
export MODHUB_AWS_REGION="${COGNITO_REGION}"
# Both targets use the fixed token while the browser OIDC flow is blocked
# (PLAN.md 5.6). The AUTH_OIDC_* exports below stay, so flipping back is
# just USE_DEV_TOKEN in plugins/modhub/src/apis.ts.
export MODHUB_DEV_TOKEN="${JWT}"
echo "  auth: fixed dev token (browser OIDC pending -- PLAN.md 5.6)"
export AUTH_SESSION_SECRET="${AUTH_SESSION_SECRET:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')}"
export AUTH_OIDC_METADATA_URL="${POOL_ID_ISSUER}/.well-known/openid-configuration"
export AUTH_OIDC_CLIENT_ID="${BACKSTAGE_CLIENT_ID}"
export AUTH_OIDC_CLIENT_SECRET="${BACKSTAGE_CLIENT_SECRET}"

cd apps/backstage
exec pnpm start
