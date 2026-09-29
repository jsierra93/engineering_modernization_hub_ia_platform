#!/usr/bin/env bash

# Rebuild what changed and apply it.
#
#   ./deploy.sh personal                          apply only
#   ./deploy.sh personal core                     rebuild that artifact, then apply (core = api, core_ops, fetch_repo, open_pr)
#   ./deploy.sh personal --all                    rebuild every Lambda, then apply
#   ./deploy.sh personal --sandbox v4             build+push the sandbox image as v4,
#                                                 record the tag in sandbox.auto.tfvars, apply
#   ./deploy.sh personal --all --sandbox v4       both
#
# The Lambda architecture comes from var.lambda_architecture in the env (override: MODHUB_LAMBDA_ARCH).
# --plan-only stops before applying.

set -euo pipefail

TARGET="${1:-}"
shift || true

TF="${TERRAFORM_BIN:-terraform}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALL_SERVICES=(core agent_phase fetch_doc)

die() { echo "error: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }

case "${TARGET}" in
  personal) ENV_DIR="infrastructure/envs"; export AWS_PROFILE="${AWS_PROFILE:-personal}" ;;
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

if [[ ${#SERVICES[@]} -gt 0 ]]; then
  ARCH="${MODHUB_LAMBDA_ARCH:-$(cd "${ENV_DIR}" && echo 'var.lambda_architecture' | "${TF}" console -no-color | tr -d '"')}"
  [[ -n "${ARCH}" ]] || die "could not read var.lambda_architecture from ${ENV_DIR} -- set MODHUB_LAMBDA_ARCH"
  echo "  lambda architecture: ${ARCH}"
fi

for SERVICE in "${SERVICES[@]:-}"; do
  [[ -n "${SERVICE}" ]] || continue
  step "Building ${SERVICE}"
  BUILD_LOG="$(mktemp)"
  if bash infrastructure/scripts/build_lambda.sh "" "${ARCH}" "${SERVICE}" >"${BUILD_LOG}" 2>&1; then
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
  ARCH="${ARCH:-$(cd "${ENV_DIR}" && echo 'var.lambda_architecture' | "${TF}" console -no-color | tr -d '"')}"
  case "${ARCH}" in arm64) PLATFORM="linux/arm64" ;; *) PLATFORM="linux/amd64" ;; esac
  docker build -q --platform "${PLATFORM}" -t "modhub-sandbox:${SANDBOX_TAG}" sandbox/ >/dev/null

  step "Pushing to ${REPO_URL}:${SANDBOX_TAG}"
  REGION="$(echo "${REGISTRY}" | sed -E 's/.*\.dkr\.ecr\.([^.]+)\..*/\1/')"
  aws ecr get-login-password --region "${REGION}" | docker login --username AWS --password-stdin "${REGISTRY}" >/dev/null
  docker tag "modhub-sandbox:${SANDBOX_TAG}" "${REPO_URL}:${SANDBOX_TAG}"
  docker push "${REPO_URL}:${SANDBOX_TAG}" | tail -1

  echo "sandbox_image_tag = \"${SANDBOX_TAG}\"" > "${ENV_DIR}/sandbox.auto.tfvars"
  echo "  sandbox_image_tag -> ${SANDBOX_TAG} (${ENV_DIR}/sandbox.auto.tfvars)"
fi

step "terraform plan (${ENV_DIR})"
cd "${ENV_DIR}"
PLAN_FILE="$([[ "${PLAN_ONLY}" == "1" ]] && echo tfplan.out || mktemp)"
PLAN_LOG="$(mktemp)"
if ! "${TF}" plan -no-color -out="${PLAN_FILE}" >"${PLAN_LOG}" 2>&1; then
  tail -40 "${PLAN_LOG}"
  rm -f "${PLAN_LOG}" "${PLAN_FILE}"
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
APPLY_LOG="$(mktemp)"
if ! "${TF}" apply -no-color "${PLAN_FILE}" >"${APPLY_LOG}" 2>&1; then
  tail -40 "${APPLY_LOG}"
  rm -f "${APPLY_LOG}" "${PLAN_FILE}"
  die "terraform apply failed"
fi
grep -E "Apply complete" "${APPLY_LOG}"
rm -f "${APPLY_LOG}" "${PLAN_FILE}"
