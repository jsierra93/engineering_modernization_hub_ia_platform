# Backstage — Engineering Modernization Hub

This is the self-service portal for the Engineering Modernization Hub: a
standard [Backstage](https://backstage.io) instance where developers submit
modernization requests through Scaffolder templates and track progress
against the `modhub/v1` API.

This is a fully local development setup. For real API interaction, you need
AWS infrastructure deployed (see `infrastructure/envs/`).

## What's here

- `packages/app` — the standard Backstage frontend shell (customized with branding).
- `packages/backend` — the standard Backstage backend shell configured with pnpm
  (this repo is a pnpm workspace).
- `plugins/modhub` and `plugins/modhub-backend` — custom plugins for modernization
  request management.
- `app-config.yaml` — configured for OIDC authentication against AWS Cognito.
- `docker-compose.yml` — runs Backstage with SQLite for local development.

## Authentication

Backstage supports two authentication methods:

- **Guest** (default) — for local development without AWS credentials.
- **OIDC** — requires AWS Cognito configuration. Set these environment variables:
  - `AUTH_OIDC_METADATA_URL`
  - `AUTH_OIDC_CLIENT_ID`
  - `AUTH_OIDC_CLIENT_SECRET`
  - `AUTH_SESSION_SECRET`

## Running it locally

### Option A — pnpm (recommended for development)

```sh
pnpm install
pnpm start
```

This starts both the frontend (`http://localhost:3000`) and backend
(`http://localhost:7007`) in watch mode. Sign in with the **guest** provider
(no credentials needed).

### Option B — Docker Compose

```sh
# Build the backend bundle on the host first:
pnpm install
pnpm tsc
pnpm build:backend

# Set required environment variables:
export MODHUB_API_BASE_URL=https://your-api-endpoint.execute-api.us-east-2.amazonaws.com
export MODHUB_NOTIFICATIONS_QUEUE_URL=https://your-sqs-queue-url
export MODHUB_AWS_REGION=us-east-2
export AUTH_SESSION_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
export AUTH_OIDC_METADATA_URL=https://cognito-idp.us-east-2.amazonaws.com/your-pool-id/.well-known/openid-configuration
export AUTH_OIDC_CLIENT_ID=your-client-id
export AUTH_OIDC_CLIENT_SECRET=your-client-secret

docker compose up --build
```

This runs the Backstage container with persistent storage for development.
Access the frontend at `http://localhost:3000` and backend at `http://localhost:7007`.

## Package manager note

The official Backstage scaffolder (`@backstage/create-app`) requires Yarn to
run and produces a Yarn workspace by default. Per `CLAUDE.md`, this repo
uses **pnpm** for all TypeScript workspaces, so immediately after scaffolding
this app the Yarn-specific files (`.yarnrc.yml`, `.yarn/`, `yarn.lock`) were
removed and replaced with `pnpm-workspace.yaml` plus a `packageManager: pnpm@...`
entry in `package.json`. The root `package.json` `workspaces` field is kept
as-is (Backstage tooling reads it for package discovery); `pnpm-workspace.yaml`
is what pnpm itself uses to resolve the workspace.

One upstream wrinkle, already worked around in `package.json`'s
`pnpm.overrides`: `@backstage/cli-module-package-manager-yarn` (a transitive
dependency of `@backstage/cli-defaults`, used only for detecting a Yarn
project) pulls in `@yarnpkg/core`, which declares a dependency on `got` via
Yarn's `patch:` protocol pointing at a relative patch file
(`~/.yarn/patches/...`) that only exists inside Yarn Berry's own monorepo.
pnpm's resolver cannot fetch that patch and fails with
`ERR_PNPM_SPEC_NOT_SUPPORTED_BY_ANY_RESOLVER`. The override
`"@yarnpkg/core>got": "npm:got@11.8.2"` forces the plain, unpatched `got`
package instead — harmless here since nothing in this app actually runs
Yarn-specific code paths. `pnpm install` has been verified to complete
successfully with this override in place.
