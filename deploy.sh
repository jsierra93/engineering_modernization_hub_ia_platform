#!/usr/bin/env bash
# Rebuild what changed and apply it.
#
#   ./deploy.sh personal                          apply only
#   ./deploy.sh personal api core_ops             rebuild those Lambdas, then apply
#   ./deploy.sh personal --all                    rebuild every Lambda, then apply
#   ./deploy.sh personal --sandbox v4             build+push the sandbox image as v4,
#                                                 point the task definition at it, apply
#   ./deploy.sh personal --all --sandbox v4       both
#
# --plan-only stops before applying.
# Note: Only personal (real AWS) environment is available. Local development uses docker compose.

set -euo pipefail

TARGET="${1:-}"
shift || true

TF="${TERRAFORM_BIN:-terraform}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALL_SERVICES=(api core_ops agent_phase fetch_repo fetch_doc open_pr)

die() { echo "error: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }

case "${TARGET}" in
  personal) ENV_DIR="infrastructure/envs/personal"; export AWS_PROFILE="${AWS_PROFILE:-personal}" ;;
  "") die "no target -- use '$(basename "$0") personal [services...]' (only personal env is available)" ;;
  *) die "unknown target '${TARGET}' -- use 'personal'" ;;
esac

SERVICES=()
SANDBOX_TAG=""
PLAN_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)      SERVICES=("${ALL_SERVICES[@]}") ;;
    --sandbox)  shift; SANDBOX_TAG="${1:-}"; [[ -n "${SANDBOX_TAG}" ]] || die "--sandbox needs a tag" ;;
    --plan-only) PLAN_ONLY=1 ;;
    -*)         die "unknown flag '$1'" ;;
    *)          SERVICES+=("$1") ;;
  esac
  shift
done

cd "${REPO_ROOT}"

for SERVICE in "${SERVICES[@]:-}"; do
  [[ -n "${SERVICE}" ]] || continue
  step "Building ${SERVICE}"
  BUILD_LOG="$(mktemp)"
  if bash infrastructure/scripts/build_lambda.sh "" arm64 "${SERVICE}" >"${BUILD_LOG}" 2>&1; then
    grep -E "^==> Done" "${BUILD_LOG}" || true
    rm -f "${BUILD_LOG}"
  else
    echo "--- last 30 lines ---"
    tail -30 "${BUILD_LOG}"
    rm -f "${BUILD_LOG}"
    die "build failed: ${SERVICE}"
  fi
done

if [[ -n "${SANDBOX_TAG}" ]]; then
  [[ "${TARGET}" == "personal" ]] || die "--sandbox only applies to the personal env"
  REPO_URL="$(cd "${ENV_DIR}" && "${TF}" output -raw sandbox_ecr_repository_url)"
  REGISTRY="${REPO_URL%%/*}"

  step "Building sandbox image ${SANDBOX_TAG}"
  docker build -q -t "modhub-sandbox:${SANDBOX_TAG}" sandbox/ >/dev/null

  step "Pushing to ${REPO_URL}:${SANDBOX_TAG}"
  REGION="$(echo "${REGISTRY}" | sed -E 's/.*\.dkr\.ecr\.([^.]+)\..*/\1/')"
  aws ecr get-login-password --region "${REGION}" | docker login --username AWS --password-stdin "${REGISTRY}" >/dev/null
  docker tag "modhub-sandbox:${SANDBOX_TAG}" "${REPO_URL}:${SANDBOX_TAG}"
  docker push "${REPO_URL}:${SANDBOX_TAG}" | tail -1

  # The ECR repo is IMMUTABLE, so a rebuilt image always needs a new tag here.
  sed -i -E "s/(sandbox_image_tag[[:space:]]*=[[:space:]]*)\"[^\"]*\"/\1\"${SANDBOX_TAG}\"/" "${ENV_DIR}/main.tf"
  echo "  sandbox_image_tag -> ${SANDBOX_TAG}"
fi

step "terraform plan (${ENV_DIR})"
cd "${ENV_DIR}"
PLAN_LOG="$(mktemp)"
if ! "${TF}" plan -no-color -out=tfplan.out >"${PLAN_LOG}" 2>&1; then
  tail -40 "${PLAN_LOG}"
  rm -f "${PLAN_LOG}"
  die "terraform plan failed"
fi
grep -E "^Plan:|No changes|will be (created|destroyed|updated)|must be replaced" "${PLAN_LOG}" | sed 's/^  # //'
rm -f "${PLAN_LOG}"

if [[ "${PLAN_ONLY}" == "1" ]]; then
  echo
  echo "plan guardado en ${ENV_DIR}/tfplan.out -- aplicar con: terraform apply tfplan.out"
  exit 0
fi

step "terraform apply"
# Piping straight into grep would report grep's exit status, not
# terraform's -- a failed apply then looks like a successful deploy.
APPLY_LOG="$(mktemp)"
if ! "${TF}" apply -no-color tfplan.out >"${APPLY_LOG}" 2>&1; then
  tail -40 "${APPLY_LOG}"
  rm -f "${APPLY_LOG}"
  die "terraform apply failed"
fi
grep -E "Apply complete" "${APPLY_LOG}"
rm -f "${APPLY_LOG}"
