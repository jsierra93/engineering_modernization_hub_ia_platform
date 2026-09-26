#!/usr/bin/env bash
# infrastructure/scripts/build_lambda.sh
#
# Packages the real `services/api` Lambda handler (Python, uv workspace)
# into a zip that infrastructure/modules/api can deploy via its
# `lambda_source_dir` variable's data.archive_file. Reads services/api and
# packages/core_py; never writes into either (that tree belongs to the
# Python agent's work, not to infrastructure/).
#
# Why not `uv export` / `uv sync --no-dev`: uv is not installed in this
# environment. Since api and core_py are both pure-Python (no compiled
# extensions of their own - only their *dependencies*, e.g. pydantic-core,
# are compiled), we copy their source trees verbatim and use `pip install
# --platform manylinux2014_<arch> --only-binary=:all:` to fetch Linux
# wheels for the third-party dependencies regardless of the host OS/Python
# running this script.
#
# Architecture defaults to arm64, matching infrastructure/modules/api's
# `lambda_architectures` default for real AWS (Graviton2, same cost
# rationale as the sandbox Fargate task in the design artifact). Pass
# x86_64 explicitly when building for Floci: empirically (2026-09-25,
# `boto3 invoke` against a real deployed function), Floci runs Lambda
# containers as the Docker host's native architecture -- it does not
# cross-emulate arm64 -- so an arm64 .so there fails to import with a
# misleading "No module named 'pydantic_core._pydantic_core'" (not an
# ImportError naming the real cause). infrastructure/envs/local overrides
# `lambda_architectures` to ["x86_64"] for exactly this reason; keep this
# script's default in sync with envs/personal (arm64), not envs/local.
#
# Usage:
#   infrastructure/scripts/build_lambda.sh [output_zip_path] [arch]
#   arch: arm64 (default) | x86_64
#
# Default output: infrastructure/scripts/build/api_lambda_real.zip

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

OUT_ZIP="${1:-${SCRIPT_DIR}/build/api_lambda_real.zip}"
ARCH="${2:-arm64}"
BUILD_DIR="$(dirname "${OUT_ZIP}")/api_lambda_src"

case "${ARCH}" in
  arm64)  MANYLINUX_PLATFORM="manylinux2014_aarch64" ;;
  x86_64) MANYLINUX_PLATFORM="manylinux2014_x86_64" ;;
  *) echo "error: unsupported arch '${ARCH}' -- use arm64 or x86_64" >&2; exit 1 ;;
esac

API_SRC="${REPO_ROOT}/services/api/src/api"
CORE_PY_SRC="${REPO_ROOT}/packages/core_py/src/core_py"

if [ ! -d "${API_SRC}" ]; then
  echo "error: ${API_SRC} not found - expected services/api's real handler" >&2
  exit 1
fi
if [ ! -d "${CORE_PY_SRC}" ]; then
  echo "error: ${CORE_PY_SRC} not found - expected packages/core_py's models" >&2
  exit 1
fi

echo "==> Cleaning build dir: ${BUILD_DIR}"
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

echo "==> Copying services/api/src/api (read-only source, not modified)"
cp -r "${API_SRC}" "${BUILD_DIR}/api"
# Drop bytecode caches picked up from the dev tree - keep the artifact clean.
find "${BUILD_DIR}/api" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "==> Copying packages/core_py/src/core_py (read-only source, not modified)"
cp -r "${CORE_PY_SRC}" "${BUILD_DIR}/core_py"
find "${BUILD_DIR}/core_py" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "==> Installing third-party dependencies (pydantic, boto3) as linux/${ARCH}, cp314 wheels"
python3 -m pip install \
  --platform "${MANYLINUX_PLATFORM}" \
  --implementation cp \
  --python-version 3.14 \
  --only-binary=:all: \
  --target "${BUILD_DIR}" \
  "pydantic>=2.7" "boto3>=1.34"

echo "==> Zipping ${BUILD_DIR} -> ${OUT_ZIP}"
mkdir -p "$(dirname "${OUT_ZIP}")"
rm -f "${OUT_ZIP}"
# Use Python's zipfile rather than the `zip` binary - not guaranteed to be
# installed (it wasn't, in the environment this script was authored in),
# whereas python3 is already required for the pip step above.
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
