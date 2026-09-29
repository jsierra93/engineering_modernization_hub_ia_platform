#!/usr/bin/env bash

# infrastructure/scripts/build_lambda.sh
#
# Packages a real Lambda service (Python, uv workspace) into a zip that
# the matching Terraform module can deploy via its `lambda_package_zip_path`
# variable. Reads services/<service> and packages/core_py; never writes
# into either (that tree belongs to the Python side, not infrastructure/).
#
# Why not `uv export` / `uv sync --no-dev`: uv is not installed in every
# environment this runs in. Since each service and core_py are pure-Python
# (no compiled extensions of their own -- only their *dependencies*, e.g.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SERVICE="${3:-api}"
ARCH="${2:-arm64}"
OUT_ZIP="${1:-${SCRIPT_DIR}/build/${SERVICE}_lambda_${ARCH}.zip}"
BUILD_DIR="$(dirname "${OUT_ZIP}")/${SERVICE}_lambda_src"

case "${ARCH}" in
  arm64)  DOCKER_PLATFORM="linux/arm64" ;;
  x86_64) DOCKER_PLATFORM="linux/amd64" ;;
  *) echo "error: unsupported arch '${ARCH}' -- use arm64 or x86_64" >&2; exit 1 ;;
esac

STRATEGY_PACKAGES=()
for strategy_dir in "${REPO_ROOT}"/strategies/*/src/*/; do
  if [ -f "${strategy_dir}strategy.marker" ]; then
    STRATEGY_PACKAGES+=("${strategy_dir%/}:$(basename "${strategy_dir}")")
  fi
done

case "${SERVICE}" in
  core)
    SERVICE_PACKAGES=(
      "${REPO_ROOT}/services/api/src/api:api"
      "${REPO_ROOT}/services/core_ops/src/core_ops:core_ops"
      "${REPO_ROOT}/services/fetch_repo/src/fetch_repo:fetch_repo"
      "${REPO_ROOT}/services/open_pr/src/open_pr:open_pr"
    )
    WORKSPACE_PACKAGES=(
      "${REPO_ROOT}/packages/core_py/src/core_py:core_py"
      "${REPO_ROOT}/strategies/_sdk/src/strategies_sdk:strategies_sdk"
      "${STRATEGY_PACKAGES[@]}"
    )
    THIRD_PARTY_DEPS=("pydantic>=2.7" "boto3>=1.34" "requests>=2.31")
    ;;
  fetch_doc)
    SERVICE_PACKAGES=("${REPO_ROOT}/services/fetch_doc/src/fetch_doc:fetch_doc")
    WORKSPACE_PACKAGES=()
    THIRD_PARTY_DEPS=("requests>=2.31")
    ;;
  agent_phase)
    SERVICE_PACKAGES=("${REPO_ROOT}/services/agent_phase/src/agent_phase:agent_phase")
    WORKSPACE_PACKAGES=(
      "${REPO_ROOT}/packages/core_py/src/core_py:core_py"
      "${REPO_ROOT}/strategies/_sdk/src/strategies_sdk:strategies_sdk"
      "${STRATEGY_PACKAGES[@]}"
    )
    THIRD_PARTY_DEPS=("strands-agents==1.57.1" "pydantic>=2.7" "boto3>=1.34")
    ;;
  *)
    echo "error: unsupported service '${SERVICE}' -- use core (api, core_ops, fetch_repo, open_pr in one artifact), fetch_doc or agent_phase" >&2
    exit 1
    ;;
esac

for pkg_pair in "${SERVICE_PACKAGES[@]}"; do
  if [ ! -d "${pkg_pair%%:*}" ]; then
    echo "error: ${pkg_pair%%:*} not found - expected the service's real handler" >&2
    exit 1
  fi
done
for pkg_pair in "${WORKSPACE_PACKAGES[@]+"${WORKSPACE_PACKAGES[@]}"}"; do
  pkg_src="${pkg_pair%%:*}"
  if [ ! -d "${pkg_src}" ]; then
    echo "error: ${pkg_src} not found - a workspace package this service depends on is missing" >&2
    exit 1
  fi
done

echo "==> Cleaning build dir: ${BUILD_DIR}"
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

for pkg_pair in "${SERVICE_PACKAGES[@]}" "${WORKSPACE_PACKAGES[@]+"${WORKSPACE_PACKAGES[@]}"}"; do
  pkg_src="${pkg_pair%%:*}"
  pkg_name="${pkg_pair##*:}"
  echo "==> Copying ${pkg_src} (read-only source, not modified)"
  cp -r "${pkg_src}" "${BUILD_DIR}/${pkg_name}"
  find "${BUILD_DIR}/${pkg_name}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
done

echo "==> Installing third-party dependencies (${THIRD_PARTY_DEPS[*]}) inside a linux/${ARCH} python:3.14-slim container"
MSYS_NO_PATHCONV=1 docker run --rm \
  --platform "${DOCKER_PLATFORM}" \
  -v "${BUILD_DIR}:/out" \
  python:3.14-slim \
  pip install --no-cache-dir --target /out "${THIRD_PARTY_DEPS[@]}"

echo "==> Zipping ${BUILD_DIR} -> ${OUT_ZIP}"
mkdir -p "$(dirname "${OUT_ZIP}")"
rm -f "${OUT_ZIP}"
python3 - "${BUILD_DIR}" "${OUT_ZIP}" <<'PYEOF'
import os
import sys
import zipfile

build_dir, out_zip = sys.argv[1], sys.argv[2]

with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _dirs, files in os.walk(build_dir):
        for name in files:
            full_path = os.path.join(root, name)
            arcname = os.path.relpath(full_path, build_dir)
            zf.write(full_path, arcname)
PYEOF

echo "==> Done: ${OUT_ZIP} ($(du -h "${OUT_ZIP}" | cut -f1))"
