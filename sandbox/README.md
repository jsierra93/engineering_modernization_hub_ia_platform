# sandbox

The deterministic execution image for the Engineering Modernization Hub
(PLAN.md task 2.1). Runs exactly one named check against a Python project
and produces real, parseable results — nothing more. Per `CLAUDE.md`:

- Invariant #3: the agent chooses neither the command nor its flags —
  only a check *name* is accepted, from a closed allowlist.
- Invariant #8: the sandbox has no credentials — no AWS SDK, no task
  role, no environment-based secrets, non-root user, no free shell.

This container does not know AWS exists. It reads a local directory and
writes to another local directory. Wiring those directories to S3 via
presigned URLs (so ECS/Fargate can hydrate `/workspace` and harvest
`/output`) is orchestration — a different task (2.3) builds that. This
image only needs the volume-mount contract described below to be usable
by whatever wiring comes next.

## Volume-mount contract

| Path | Direction | Contents |
|---|---|---|
| `/workspace` | in (read/write) | The Python project to check. `install` writes packages/build artifacts here (e.g. `*.egg-info`); `unit_tests`/`lint` do not modify source files. |
| `/output` | out (write) | Check results. Always written, whether the check passed or failed. |

`/output` contents by check:

- `install` → `install.<requirements-file>.log` per `requirements*.txt` found, and/or `install.pyproject.log` if a `pyproject.toml` exists. `install.log` if neither is present (nothing to do, exit 0).
- `unit_tests` → `junit.xml` (real JUnit XML via `pytest --junitxml=`, the file `core_ops` — a different task, 2.4 — parses to compute the verdict) plus `unit_tests.log` with full stdout/stderr. If pytest fails before producing a report (e.g. a collection error), `unit_tests.error` explains that explicitly.
- `lint` → `lint.json` (ruff's JSON report) plus `lint.log` with full stdout/stderr.

## Exit codes

- `0` — the check ran and passed.
- `1` — the check ran and failed (a test failed, ruff found issues, `pip install` failed).
- `2` — usage/configuration error: unknown check name, missing/empty `/workspace`. Never confused with "the check ran and failed."

## Checks

Exactly three, matching `strategies/python_pydantic_v2/src/python_pydantic_v2/manifest.py`'s `checks=["install", "unit_tests", "lint"]`. Any other argument is refused by `entrypoint.py` before any subprocess runs — there is no code path from an unrecognized argument to command execution.

- **`install`** — `pip install --user -r <requirements*.txt>` for each matching file, and/or `pip install --user -e .` if `pyproject.toml` exists. Installs into the non-root user's own site-packages; no virtualenv needed since the image is single-purpose.
- **`unit_tests`** — `pytest /workspace --junitxml=/output/junit.xml -v`. This is the load-bearing check: the JUnit output is what the platform's invariant checker (suite can only grow, never shrink — CLAUDE.md invariant #2) reads.
- **`lint`** — `ruff check /workspace --output-format=json --output-file=/output/lint.json`. Non-blocking per the five-state table (`COMPLETADO_PARCIALMENTE` allows a failing `lint`), but still a clear pass/fail exit code.

## Architecture (build arg, not a hardcoded assumption)

`Dockerfile` takes `ARG BUILD_PLATFORM` (default `linux/amd64`). Locally,
this host is `linux/amd64` (confirmed via `docker version` / `uname -m`),
which is why that's the default — a lesson from Fase 1, where an arm64
Lambda image built fine but silently misbehaved under Floci because
local Docker does not cross-emulate arm64. Building for the host's own
architecture keeps local verification fast and faithful.

Real AWS deployment targets **linux/arm64 (Graviton)** for cost, matching
the sandbox Fargate task's own justification in the design (see 2.1-tf
in `PLAN.md`). That's a different `BUILD_PLATFORM` value at build time —
nothing in the Dockerfile assumes one architecture over the other.

```bash
# Local (this host, linux/amd64 — the default)
docker build -t modhub-sandbox:local sandbox/

# For real AWS/Graviton deployment (done by the Terraform task, 2.1-tf)
docker build --build-arg BUILD_PLATFORM=linux/arm64 -t modhub-sandbox:arm64 sandbox/
```

## Manual build and run

From the repo root:

```bash
docker build -t modhub-sandbox:local sandbox/

# Windows paths: use the Windows-style absolute path for -v, not a
# POSIX /tmp path, or Docker Desktop will mount the wrong filesystem.
WS="$(pwd)/sandbox/fixtures/sample_repo"
OUT="/some/writable/output/dir"
mkdir -p "$OUT"

docker run --rm -v "$WS:/workspace" -v "$OUT:/output" modhub-sandbox:local install
docker run --rm -v "$WS:/workspace" -v "$OUT:/output" modhub-sandbox:local unit_tests
docker run --rm -v "$WS:/workspace" -v "$OUT:/output" modhub-sandbox:local lint

cat "$OUT/junit.xml"
```

An unrecognized check name is refused with exit code `2`:

```bash
docker run --rm -v "$WS:/workspace" -v "$OUT:/output" modhub-sandbox:local anything_else
# unknown check 'anything_else'. known checks: install, unit_tests, lint
```

## Fixture: `fixtures/sample_repo/`

A minimal throwaway Python project used only to self-verify this image
(PLAN.md 2.1's "Hecho cuando"). It has:

- `src/calc.py` — three trivial functions (`add`, `divide`, `is_even`).
- `tests/test_calc.py` — **three** pytest test functions: two pass
  (`test_add`, `test_is_even`), and **one is an intentional failure**
  (`test_divide_intentionally_wrong` asserts `divide(10, 2) == 6`, which
  is false). This is deliberate, not a mistake left behind: it proves
  the sandbox reports a genuine failure (`unit_tests` exits `1`, and the
  JUnit shows `failures="1"`) rather than a check that always reports
  green — the exact property `core_ops`'s real-JUnit verdict depends on
  in the rest of Fase 2.
- `pyproject.toml` — a real (setuptools/PEP 517) packaging manifest, so
  `install` exercises the `pip install -e .` code path, not just the
  `requirements.txt` path.

Verified locally (this host, `linux/amd64`):

- `install` → exit `0`, `install.pyproject.log` shows a successful
  editable install.
- `unit_tests` → exit `1` (one real failure), `junit.xml` present and
  parseable: `tests="3" failures="1" errors="0" skipped="0"`.
- `lint` → exit `1`, `lint.json` has real ruff findings (JSON array).
- An unknown check name (e.g. `deploy`) → exit `2`, nothing executed.

If you rerun the fixture locally, delete `fixtures/sample_repo/*.egg-info`
and any `__pycache__` directories afterward — `install` and `unit_tests`
write those into the mounted workspace, and they don't belong in git.
