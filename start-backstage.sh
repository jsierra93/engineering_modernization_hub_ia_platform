#!/usr/bin/env bash

#
# Starts Backstage against the deployed AWS environment (needs AWS_PROFILE credentials):
#
#   ./start-backstage.sh
#
# Reads the Terraform outputs, mints a real Cognito token for the demo user
# and starts Backstage pointed at the deployed API with that token.

set -euo pipefail

TF="${TERRAFORM_BIN:-terraform}"
TEST_USERNAME="${MODHUB_TEST_USERNAME:-jsierra93@hotmail.com}"
TEST_PASSWORD="${MODHUB_TEST_PASSWORD:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(18) + "aA1!")')}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="infrastructure/envs"
AWS_REGION_NAME="${AWS_DEFAULT_REGION:-us-east-2}"
export AWS_PROFILE="${AWS_PROFILE:-personal}"

die() { echo "error: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }

cd "${REPO_ROOT}"

step "Reading Terraform outputs (${ENV_DIR})"
TF_OUT="$(cd "${ENV_DIR}" && "${TF}" output -json)" || die "terraform output failed -- has the environment been applied?"
py_get() { python3 -c "import json,sys; print(json.loads(sys.argv[1])['$1']['value'])" "${TF_OUT}"; }

API_BASE_URL="$(py_get api_endpoint)"
API_BASE_URL="${API_BASE_URL%/}"
POOL_ID_ISSUER="$(py_get cognito_issuer_url)"
POOL_ID="${POOL_ID_ISSUER##*/}"
CLI_CLIENT_ID="$(py_get cognito_cli_client_id)"
BACKSTAGE_CLIENT_ID="$(py_get cognito_backstage_client_id)"
BACKSTAGE_CLIENT_SECRET="$(py_get cognito_backstage_client_secret)"
NOTIFICATIONS_QUEUE_URL="$(py_get notifications_queue_url)"

echo "  API:            ${API_BASE_URL}"
echo "  Cognito issuer: ${POOL_ID_ISSUER}"

step "Minting a Cognito token for ${TEST_USERNAME}"
JWT="$(python3 - "${POOL_ID}" "${CLI_CLIENT_ID}" "${TEST_USERNAME}" "${TEST_PASSWORD}" "${AWS_REGION_NAME}" <<'PYEOF'
import boto3, sys
pool_id, client_id, username, password, region = sys.argv[1:6]
c = boto3.client("cognito-idp", region_name=region)
c.admin_set_user_password(UserPoolId=pool_id, Username=username, Password=password, Permanent=True)
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

step "Starting Backstage"
export MODHUB_API_BASE_URL="${API_BASE_URL}"
export MODHUB_NOTIFICATIONS_QUEUE_URL="${NOTIFICATIONS_QUEUE_URL}"
export MODHUB_AWS_REGION="${AWS_REGION_NAME}"
export MODHUB_DEV_TOKEN="${JWT}"
echo "  auth: fixed dev token (browser OIDC pending)"
export AUTH_SESSION_SECRET="${AUTH_SESSION_SECRET:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')}"
export AUTH_OIDC_METADATA_URL="${POOL_ID_ISSUER}/.well-known/openid-configuration"
export AUTH_OIDC_CLIENT_ID="${BACKSTAGE_CLIENT_ID}"
export AUTH_OIDC_CLIENT_SECRET="${BACKSTAGE_CLIENT_SECRET}"

cd apps/backstage
exec pnpm start
