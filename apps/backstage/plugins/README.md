# The Plugins Folder

This is where the platform's own Backstage plugins live, each in its own
subfolder — the standard Backstage layout (see `apps/backstage/README.md`).

**Empty for now, on purpose.** `plugins/modhub` (frontend) and
`plugins/modhub-backend` (backend) are scaffolded in Fase 5 of `PLAN.md`,
tasks 5.2/5.3/5.4 — after the `modhub/v1` API exists (Fase 1) and the
`modhub-backstage` Cognito app client exists (Fase 4, task 4.1-tf). Building
either plugin before those exist would mean scaffolding against endpoints and
credentials that are not there yet.

To create a plugin here once its dependencies land, go to the
`apps/backstage/` root and run `pnpm new`, following the on-screen
instructions. See also the [Backstage plugin marketplace](https://backstage.io/plugins).
