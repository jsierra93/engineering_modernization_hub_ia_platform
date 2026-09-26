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
# --platform manylinux2014_aarch64 --only-binary=:all:` to fetch Linux
# wheels for the third-party dependencies regardless of the host OS/Python
# running this script. That matters here because the host is Windows and
# the Lambda runtime (real AWS, or Floci's Docker-backed emulation) is
# Linux/arm64 -- matching infrastructure/modules/api's `lambda_architectures`
# default (Graviton2, same cost rationale as the sandbox Fargate task).
# cp314 manylinux2014_aarch64 wheels confirmed to exist for pydantic-core
# as of 2026-09-25 before this was pinned -- not assumed.
#
# Usage:
#   infrastructure/scripts/build_lambda.sh [output_zip_path]
#
# Default output: infrastructure/scripts/build/api_lambda_real.zip

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

OUT_ZIP="${1:-${SCRIPT_DIR}/build/api_lambda_real.zip}"
BUILD_DIR="$(dirname "${OUT_ZIP}")/api_lambda_src"

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

echo "==> Installing third-party dependencies (pydantic, boto3) as linux/arm64, cp314 wheels"
python3 -m pip install \
  --platform manylinux2014_aarch64 \
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
