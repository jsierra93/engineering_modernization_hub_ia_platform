# Runs the WHOLE Backstage instance (frontend + backend, dev mode) inside a
# clean Linux container -- not a production bundle.
#
# Why dev mode instead of a production build: `backstage-cli package build`
# for a "bundled" app package internally shells out to a hardcoded
# `yarn run build`, which corepack correctly refuses to run against a
# pnpm-managed root (a real, confirmed backstage-cli/pnpm gap -- see
# https://github.com/backstage/backstage/issues/25362). That happens
# identically inside this container or on any host, regardless of OS --
# it is not the Windows-specific issue this Dockerfile otherwise exists to
# route around (see below). Dev mode (`pnpm start`, this image's CMD) uses
# its own dev-server bundler and never hits that code path.
#
# STATUS (2026-09-26): the backend (:7007) runs correctly in this
# container -- confirmed via `docker compose up` against Floci, all
# plugins including modhub-backend initialize, real HTTP responses. The
# frontend dev server, however, has an unresolved container-specific
# hang: it accepts TCP connections (confirmed via socat, added below to
# route around its loopback-only bind) but never responds to an HTTP
# request, even queried from inside the same container/process
# namespace with no network involved. Not debugged further because the
# ROOT CAUSES this container was meant to route around -- a pnpm
# virtual-store path exceeding Windows' MAX_PATH, a stray global Yarn
# shadowing corepack, and pnpm materializing more than one physical
# @types/react copy -- all got fixed directly in this repo instead
# (see ../../.npmrc and packages/app/package.json's pinned
# @mui/material@5/@material-ui/styles/@emotion/react). Those fixes are
# repo-level (committed, not machine-specific), so `pnpm start` on the
# host now works cleanly without this container. Kept here, working for
# the backend at least, in case full containerization is revisited.
#
# Build and run from the repo root at apps/backstage/ (same context
# docker-compose.yml uses):
#   docker build -f packages/backend/Dockerfile -t modhub-backstage .

FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 make g++ libsqlite3-dev socat \
    && rm -rf /var/lib/apt/lists/*

RUN corepack enable

WORKDIR /app
COPY . .

RUN pnpm install --frozen-lockfile

EXPOSE 3000 7007

# See entrypoint.sh's own header: the frontend dev server binds to
# loopback only, with no way to override it in this backstage-cli
# version -- socat bridges the container's external interface to it.
ENTRYPOINT ["sh", "packages/backend/entrypoint.sh"]
