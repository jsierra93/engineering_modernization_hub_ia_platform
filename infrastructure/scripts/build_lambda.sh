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
# pydantic-core, are compiled), we copy their source trees verbatim and use
# `pip install --platform manylinux2014_<arch> --only-binary=:all:` to fetch
# Linux wheels for the third-party dependencies regardless of the host
# OS/Python running this script.
#
# Architecture defaults to arm64, matching each module's `lambda_architectures`
# default for real AWS (Graviton2, same cost rationale as the sandbox
# Fargate task in the design artifact). Pass x86_64 explicitly when building
# for Floci: empirically (2026-09-25, `boto3 invoke` against a real deployed
# function), Floci runs Lambda containers as the Docker host's native
# architecture -- it does not cross-emulate arm64 -- so an arm64 .so there
# fails to import with a misleading "No module named
# 'pydantic_core._pydantic_core'" (not an ImportError naming the real
# cause). infrastructure/envs/local overrides `lambda_architectures` to
# ["x86_64"] for exactly this reason; keep this script's default in sync
# with envs/personal (arm64), not envs/local.
#
# Usage:
#   infrastructure/scripts/build_lambda.sh [output_zip_path] [arch] [service]
#   arch:    arm64 (default) | x86_64
#   service: api (default) | fetch_repo | core_ops | fetch_doc | agent_phase | open_pr
#
# Default output: infrastructure/scripts/build/<service>_lambda_<arch>.zip
# -- the architecture is part of the default filename on purpose: building
# both arm64 (envs/personal, real AWS) and x86_64 (envs/local, Floci) for
# the same service must never let one silently overwrite the other.

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

# WORKSPACE_PACKAGES: "src_dir:package_name" pairs, every workspace
# package this service's handler actually imports at runtime -- NOT every
# workspace package that exists (fetch_doc, for instance, imports none of
# them; agent_phase imports four). Each is copied read-only, never
# modified by this script.
case "${SERVICE}" in
  api)
    SERVICE_SRC="${REPO_ROOT}/services/api/src/api"
    SERVICE_PKG_NAME="api"
    # strategies_sdk/python_pydantic_v2: Fase 4's objective resolver
    # (api/strategy_lookup.py) needs the same registered-strategy catalog
    # agent_phase uses, to build the resolver's closed candidate list.
    WORKSPACE_PACKAGES=(
      "${REPO_ROOT}/packages/core_py/src/core_py:core_py"
      "${REPO_ROOT}/strategies/_sdk/src/strategies_sdk:strategies_sdk"
      "${REPO_ROOT}/strategies/python_pydantic_v2/src/python_pydantic_v2:python_pydantic_v2"
    )
    THIRD_PARTY_DEPS=("pydantic>=2.7" "boto3>=1.34")
    ;;
  fetch_repo)
    SERVICE_SRC="${REPO_ROOT}/services/fetch_repo/src/fetch_repo"
    SERVICE_PKG_NAME="fetch_repo"
    WORKSPACE_PACKAGES=("${REPO_ROOT}/packages/core_py/src/core_py:core_py")
    THIRD_PARTY_DEPS=("pydantic>=2.7" "boto3>=1.34" "requests>=2.31")
    ;;
  core_ops)
    SERVICE_SRC="${REPO_ROOT}/services/core_ops/src/core_ops"
    SERVICE_PKG_NAME="core_ops"
    WORKSPACE_PACKAGES=("${REPO_ROOT}/packages/core_py/src/core_py:core_py")
    THIRD_PARTY_DEPS=("pydantic>=2.7" "boto3>=1.34")
    ;;
  fetch_doc)
    SERVICE_SRC="${REPO_ROOT}/services/fetch_doc/src/fetch_doc"
    SERVICE_PKG_NAME="fetch_doc"
    # Zero workspace/core_py dependency on purpose -- CLAUDE.md's
    # permissions table: this service gets no AWS permissions, ever, and
    # depending on core_py (which pulls in boto3) would blur that even at
    # the packaging level.
    WORKSPACE_PACKAGES=()
    THIRD_PARTY_DEPS=("requests>=2.31")
    ;;
  agent_phase)
    SERVICE_SRC="${REPO_ROOT}/services/agent_phase/src/agent_phase"
    SERVICE_PKG_NAME="agent_phase"
    WORKSPACE_PACKAGES=(
      "${REPO_ROOT}/packages/core_py/src/core_py:core_py"
      "${REPO_ROOT}/strategies/_sdk/src/strategies_sdk:strategies_sdk"
      "${REPO_ROOT}/strategies/python_pydantic_v2/src/python_pydantic_v2:python_pydantic_v2"
    )
    # strands-agents pulls in a real dependency tree (its own transitive
    # deps, not just the two obvious ones) -- pinned to the exact version
    # in this workspace's lockfile so a build never silently drifts to a
    # newer strands-agents than what was actually tested against.
    THIRD_PARTY_DEPS=("strands-agents==1.57.1" "pydantic>=2.7" "boto3>=1.34")
    ;;
  open_pr)
    SERVICE_SRC="${REPO_ROOT}/services/open_pr/src/open_pr"
    SERVICE_PKG_NAME="open_pr"
    WORKSPACE_PACKAGES=("${REPO_ROOT}/packages/core_py/src/core_py:core_py")
    THIRD_PARTY_DEPS=("pydantic>=2.7" "boto3>=1.34" "requests>=2.31")
    ;;
  *)
    echo "error: unsupported service '${SERVICE}' -- use api, fetch_repo, core_ops, fetch_doc, agent_phase or open_pr" >&2
    exit 1
    ;;
esac

if [ ! -d "${SERVICE_SRC}" ]; then
  echo "error: ${SERVICE_SRC} not found - expected services/${SERVICE}'s real handler" >&2
  exit 1
fi
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

echo "==> Copying services/${SERVICE}/src/${SERVICE_PKG_NAME} (read-only source, not modified)"
cp -r "${SERVICE_SRC}" "${BUILD_DIR}/${SERVICE_PKG_NAME}"
# Drop bytecode caches picked up from the dev tree - keep the artifact clean.
find "${BUILD_DIR}/${SERVICE_PKG_NAME}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

for pkg_pair in "${WORKSPACE_PACKAGES[@]+"${WORKSPACE_PACKAGES[@]}"}"; do
  pkg_src="${pkg_pair%%:*}"
  pkg_name="${pkg_pair##*:}"
  echo "==> Copying ${pkg_src} (read-only source, not modified)"
  cp -r "${pkg_src}" "${BUILD_DIR}/${pkg_name}"
  find "${BUILD_DIR}/${pkg_name}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
done

# Real bug hit building agent_phase (2026-09-26), not hypothetical: plain
# `pip install --platform manylinux2014_x86_64 --python-version 3.14` from
# this Windows host still evaluates dependency environment markers (e.g.
# strands-agents' transitive `mcp` package requiring `pywin32; sys_platform
# == "win32"`) against the HOST's sys_platform, not the target's --
# `--platform` only steers wheel *tag* selection, not marker evaluation.
# Result: pip demands a Windows-only package while building a Linux
# artifact, and fails outright. Running the install inside a real Linux
# container sidesteps this at the root instead of patching around it with
# fragile pip flags -- sys_platform is genuinely "linux" in there.
echo "==> Installing third-party dependencies (${THIRD_PARTY_DEPS[*]}) inside a linux/${ARCH} python:3.14-slim container"
# MSYS_NO_PATHCONV=1: Git Bash on Windows mangles the -v HOST:CONTAINER
# argument by trying to path-convert both sides (breaking the container
# side, "/out"). Confirmed empirically, 2026-09-26 -- without it, the
# container sees "/out" as nonexistent even though the flag parses. Also
# confirmed: the host path must resolve under a real Windows drive Docker
# Desktop shares (e.g. /c/Users/...) -- /tmp is Git Bash's own overlay, not
# a path Docker Desktop can see, and silently binds an empty volume instead
# of erroring.
MSYS_NO_PATHCONV=1 docker run --rm \
  --platform "${DOCKER_PLATFORM}" \
  -v "${BUILD_DIR}:/out" \
  python:3.14-slim \
  pip install --no-cache-dir --target /out "${THIRD_PARTY_DEPS[@]}"

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
