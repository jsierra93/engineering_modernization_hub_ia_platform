# syntax=docker/dockerfile:1
#
# Sandbox execution image (PLAN.md task 2.1).
#
# Runs exactly one named check (`install`, `unit_tests`, `lint`) against a
# workspace mounted at /workspace, writing results to /output. No AWS SDK,
# no AWS credentials, no task role, no free shell — see CLAUDE.md invariant
# #3 ("checks are named, and their command comes from the strategy") and
# invariant #8 ("the sandbox has no credentials... non-root").
#
# --- Architecture ---
# BUILD_PLATFORM is an explicit build ARG (default: this host's own
# native platform, linux/amd64 — confirmed via `docker version` /
# `uname -m` on this machine) so the target architecture is a deliberate
# choice, never an assumption baked into the base image tag. Pass it
# explicitly to build the other way:
#   docker build --build-arg BUILD_PLATFORM=linux/arm64 -t sandbox:arm64 .
# `python:3.14-slim` is a multi-arch manifest, so BuildKit resolves the
# right underlying image for whichever platform is requested — nothing
# here hardcodes amd64 or arm64.
#
# Locally we default to linux/amd64 because that is this host's native
# architecture: Floci/local Docker does not cross-emulate arm64 (a Fase 1
# lesson — an arm64 Lambda image ran fine under `docker run` on an arm64
# CI runner but silently misbehaved under Floci on this amd64 host).
# Building for the host's own arch keeps local verification fast and
# faithful.
#
# Real AWS deployment targets linux/arm64 (Graviton) for cost, matching
# the sandbox Fargate task's own justification in the design (see 2.1-tf
# in PLAN.md / the architecture artifact). That is simply a different
# value of BUILD_PLATFORM supplied by Terraform/CI's build pipeline —
# never a hardcoded single-architecture assumption in this file.
ARG BUILD_PLATFORM=linux/amd64

FROM --platform=${BUILD_PLATFORM} python:3.14-slim AS sandbox

# Keep pip/python quiet and predictable; do not write .pyc cache clutter
# into the mounted /workspace.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Tooling needed to actually run the checks. No AWS CLI, no boto3, no
# credentials helper of any kind — the sandbox never talks to AWS
# directly (CLAUDE.md invariant #8).
RUN pip install --no-cache-dir \
        pytest \
        pytest-json-report \
        ruff

# Non-root user. No task role, no env vars carrying secrets, no sudo.
RUN groupadd --gid 10001 sandbox \
    && useradd --uid 10001 --gid sandbox --home-dir /home/sandbox --create-home --shell /usr/sbin/nologin sandbox

# Fixed, local-only I/O contract: /workspace is the project to check
# (read/write — checks like `install` need to create a virtualenv-less
# site-packages, and generated artifacts belong there), /output is where
# results land. Both are plain directories the orchestrator mounts or
# copies into/out of — no S3, no presigned URLs, no AWS awareness inside
# this container (that wiring is task 2.3, owned elsewhere).
RUN mkdir -p /workspace /output \
    && chown -R sandbox:sandbox /workspace /output

COPY --chown=sandbox:sandbox entrypoint.py /usr/local/bin/entrypoint.py
RUN chmod 0555 /usr/local/bin/entrypoint.py

WORKDIR /workspace
USER sandbox

# No shell entrypoint, no CMD default that runs anything implicitly.
# Exactly one argument is accepted: the check name.
ENTRYPOINT ["python3", "/usr/local/bin/entrypoint.py"]
