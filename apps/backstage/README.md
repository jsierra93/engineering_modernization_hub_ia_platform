# Backstage — Engineering Modernization Hub

This is the self-service portal for the Engineering Modernization Hub: a
standard [Backstage](https://backstage.io) instance (scaffolded with
`@backstage/create-app`, standard `packages/app` + `packages/backend` +
`plugins/*` layout), where a developer will eventually submit a modernization
request through a Scaffolder template and track its progress against the
`modhub/v1` API.

See the root `CLAUDE.md` for the platform's architecture and `PLAN.md` for
the phased build order. This instance corresponds to **PLAN.md task 5.1**
(base app skeleton) — nothing beyond the skeleton is implemented here yet.

## What's here right now

- `packages/app` — the standard Backstage frontend shell (unmodified from
  the scaffolder defaults beyond branding).
- `packages/backend` — the standard Backstage backend shell, with a
  `Dockerfile` adapted to use pnpm instead of the scaffolder's default Yarn
  (this repo is a pnpm workspace, per `CLAUDE.md`).
- `plugins/` — empty on purpose. See `plugins/README.md`.
- `app-config.yaml` — includes a placeholder `auth.providers.oidc` block for
  logging in against the `modhub-backstage` Cognito app client. The values
  are unset TODOs (`TODO-set-after-cognito-terraform-apply`), not real
  credentials — Cognito does not exist yet (`PLAN.md` task 4.1-tf).
- `docker-compose.yml` — runs the backend for local development, backed by
  SQLite (`better-sqlite3`), which is what `app-config.yaml` already
  defaults to. Postgres (used in `app-config.production.yaml`) is
  unnecessary for a single-user prototype demo.

## What's explicitly NOT here yet

- **No working login.** The `oidc` auth provider is a config placeholder,
  not a wired-up provider — it needs `@backstage/plugin-auth-backend-module-oidc-provider`
  added to `packages/backend` and a real Cognito user pool
  (`infrastructure/modules/identity`, `PLAN.md` 4.1-tf). Until then, the
  `guest` provider is what actually works for local development.
- **No `plugins/modhub` or `plugins/modhub-backend`.** Those are `PLAN.md`
  tasks 5.2, 5.3 and 5.4 — the Scaffolder template, the `modhub:create-run`
  action, the Modernizaciones page, and the SQS/Notifications/Signals
  integration. They depend on a live `modhub/v1` API and a real Cognito user
  pool, neither of which exist yet. See `plugins/README.md`.

## Running it locally

### Option A — pnpm (recommended while iterating)

```sh
pnpm install
pnpm start
```

This starts both the frontend (`http://localhost:3000`) and backend
(`http://localhost:7007`) in watch mode. Sign in with the **guest**
provider — the `oidc` provider is not wired up yet (see above).

### Option B — Docker Compose

```sh
# Build the backend bundle on the host first (packages/backend/Dockerfile
# expects packages/backend/dist/{skeleton,bundle}.tar.gz to already exist):
pnpm install
pnpm tsc
pnpm build:backend

docker compose up --build
```

This runs only the backend container, listening on `http://localhost:7007`.
There is no separate frontend container in this prototype — see
`packages/backend/Dockerfile`'s header comment for the full build sequence
`docker compose` assumes has already run on the host.

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
