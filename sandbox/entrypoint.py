#!/usr/bin/env python3
"""Sandbox entrypoint — runs exactly one named check.

CLAUDE.md invariant #3: "Checks are named, and their command comes from
the strategy. The agent chooses neither the command nor its flags. There
is no free shell in the sandbox." This script is the enforcement point
for that invariant at the container level: it accepts a single
positional argument — one of a small, hardcoded allowlist of check
names — and refuses anything else. There is no way to pass an arbitrary
command through this entrypoint.

I/O contract — two supported modes, chosen at run time by whether the
WORKSPACE_GET_URL/JUNIT_PUT_URL env vars are set:

  Local mount mode (no env vars set): /workspace and /output are
  read/write bind mounts the caller set up. This is the mode used for
  everything in this file's own README/fixture-based verification.

  Presigned-URL mode (CLAUDE.md invariant #8: "access to its own run
  only through presigned URLs"): still no AWS SDK, no AWS credentials,
  ever — a presigned URL is a plain HTTPS GET/PUT that happens to carry
  a one-time-use signature in its query string, nothing more. If
  WORKSPACE_GET_URL is set, this script downloads that URL (a single
  tar.gz, built by fetch_repo — a presigned URL only ever names one S3
  object, and the workspace is many files, hence one consolidated
  archive) and extracts it into /workspace before running the check,
  using the same tar-slip protections as `fetch_repo.sanitize` (this
  image has no dependency on that package, so the check is duplicated
  here, deliberately conservative, rather than trusting an archive that
  already passed through one sanitization pass upstream). If
  JUNIT_PUT_URL is set and /output/junit.xml exists after the check
  runs, it's PUT to that URL. Uses only the standard library
  (`urllib.request`) — no `requests`, to keep this image's dependency
  surface minimal (it already has zero AWS SDK; no reason to add an HTTP
  client dependency either).

Exit code contract:
  0   the check passed
  1   the check ran and failed (e.g. a test failed, lint found issues)
  2   usage/configuration error (unknown check name, missing workspace,
      a presigned URL fetch/push failure, etc.) — never confused with
      "the check ran and failed"
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

WORKSPACE = Path("/workspace")
OUTPUT = Path("/output")

WORKSPACE_GET_URL_ENV = "WORKSPACE_GET_URL"
JUNIT_PUT_URL_ENV = "JUNIT_PUT_URL"

# Same limits as fetch_repo.sanitize, duplicated rather than shared (this
# image has no dependency on that package -- see module docstring).
MAX_TOTAL_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 50 * 1024 * 1024


class WorkspaceFetchError(Exception):
    """Downloading or safely extracting WORKSPACE_GET_URL failed."""


def _is_within_root(candidate: str) -> bool:
    if candidate.startswith("/") or candidate.startswith("\\"):
        return False
    if len(candidate) >= 2 and candidate[1] == ":":
        return False
    depth = 0
    for part in candidate.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                return False
        else:
            depth += 1
    return True


def fetch_workspace(url: str) -> None:
    """Download the consolidated workspace archive and extract it into
    /workspace, with the same tar-slip protections fetch_repo already
    applied once upstream (belt and suspenders: this image never trusts
    an archive just because it arrived over a presigned URL)."""

    try:
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 - fixed https presigned URL, not user input
            archive_bytes = resp.read()
    except Exception as exc:  # noqa: BLE001 - re-raised as our own type
        raise WorkspaceFetchError(f"failed to download workspace: {exc}") from exc

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    try:
        import io

        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            for member in archive:
                if member.issym() or member.islnk() or member.isdev():
                    raise WorkspaceFetchError(f"rejected archive member {member.name!r}: not a regular file")
                if not (member.isfile() or member.isdir()):
                    raise WorkspaceFetchError(f"rejected archive member {member.name!r}: unsupported type")
                if not _is_within_root(member.name):
                    raise WorkspaceFetchError(f"rejected archive member {member.name!r}: escapes extraction root")
                if member.isdir():
                    continue
                if member.size > MAX_SINGLE_FILE_BYTES:
                    raise WorkspaceFetchError(f"rejected archive member {member.name!r}: too large")
                total_bytes += member.size
                if total_bytes > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise WorkspaceFetchError("workspace archive exceeds the total decompressed size limit")
                archive.extract(member, path=WORKSPACE, filter="data")
    except tarfile.TarError as exc:
        raise WorkspaceFetchError(f"workspace archive is not a valid tar.gz: {exc}") from exc


def push_junit(url: str) -> None:
    """PUT /output/junit.xml to a presigned URL, if it exists. Silent
    no-op if the check that ran doesn't produce one (e.g. `lint`) --
    this is called unconditionally after every check."""

    junit_path = OUTPUT / "junit.xml"
    if not junit_path.exists():
        return

    data = junit_path.read_bytes()
    request = urllib.request.Request(url, data=data, method="PUT")
    try:
        with urllib.request.urlopen(request, timeout=60):  # noqa: S310 - fixed https presigned URL
            pass
    except Exception as exc:  # noqa: BLE001 - re-raised as our own type
        raise WorkspaceFetchError(f"failed to push {junit_path} to presigned URL: {exc}") from exc

# The complete, closed set of checks this image will ever run. Adding a
# check means editing this file and rebuilding the image — it is never
# something a caller can inject at run time.
KNOWN_CHECKS = ("install", "unit_tests", "lint")


def _emit(event: str, **fields) -> None:
    """One JSON line to stdout, which the awslogs driver ships to
    CloudWatch. Mirrors core_py.observability.log_event's shape, but
    inlined: this image deliberately has no dependency on core_py."""
    import json

    print(json.dumps({"event": event, **fields}, default=str), flush=True)


def _write_log(name: str, result: subprocess.CompletedProcess) -> None:
    """Persist stdout/stderr for a check under /output, and echo to the
    container's stdout -- /output does not survive the task, so CloudWatch
    is the only place this is readable after the fact."""
    body = (
        f"$ {' '.join(result.args)}\n"
        f"exit_code={result.returncode}\n\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}\n"
    )
    (OUTPUT / f"{name}.log").write_text(body, encoding="utf-8")
    _emit("sandbox.check_output", check=name, exit_code=result.returncode)
    print(body, flush=True)


def _run(cmd: list[str], cwd: Path = WORKSPACE) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        # No shell=True anywhere: cmd is always a fixed argv list built
        # entirely inside this file, never from user/agent input.
    )


def check_install() -> int:
    """Install the project's own dependencies (not this image's tooling).

    Handles both a requirements*.txt project and a pyproject.toml
    (PEP 517/518) project. Installs into the image's user site-packages
    (no AWS index, no credentials — plain PyPI, which is the documented
    "modo public" network posture).
    """
    requirements = sorted(WORKSPACE.glob("requirements*.txt"))
    pyproject = WORKSPACE / "pyproject.toml"

    ran_any = False
    overall_rc = 0

    for req_file in requirements:
        result = _run([sys.executable, "-m", "pip", "install", "--user", "-r", str(req_file)])
        _write_log(f"install.{req_file.name}", result)
        ran_any = True
        if result.returncode != 0:
            overall_rc = result.returncode

    if pyproject.exists():
        result = _run([sys.executable, "-m", "pip", "install", "--user", "-e", "."])
        _write_log("install.pyproject", result)
        ran_any = True
        if result.returncode != 0:
            overall_rc = result.returncode

    if not ran_any:
        (OUTPUT / "install.log").write_text(
            "No requirements*.txt and no pyproject.toml found in /workspace; "
            "nothing to install.\n",
            encoding="utf-8",
        )
        # Nothing to install is not itself a failure — a strategy may
        # target a project with zero third-party dependencies.
        return 0

    return overall_rc


def check_unit_tests() -> int:
    """Run pytest, producing real JUnit XML at /output/junit.xml.

    This is the file core_ops parses to compute the verdict (invariant
    #1/#2/#10) — the format must be genuine JUnit, not a hand-rolled
    summary, and pytest's own --junitxml writer is what guarantees that.
    """
    # The state machine runs one check per container and containers share
    # no filesystem, so a separately-run `install` check would not reach
    # this one. Installing here is what makes the run test the project
    # rather than a chain of ImportErrors.
    install_rc = check_install()
    if install_rc != 0:
        _emit("sandbox.install_failed_before_tests", exit_code=install_rc)
        return install_rc

    junit_path = OUTPUT / "junit.xml"
    result = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(WORKSPACE),
            f"--junitxml={junit_path}",
            "-v",
        ]
    )
    _write_log("unit_tests", result)

    if not junit_path.exists():
        # pytest can exit non-zero for reasons that never produce a
        # report (e.g. a collection error before any test runs). Make
        # that failure mode explicit rather than silently missing.
        (OUTPUT / "unit_tests.error").write_text(
            "pytest did not produce /output/junit.xml — see unit_tests.log.\n",
            encoding="utf-8",
        )
        return result.returncode or 1

    return result.returncode


def check_lint() -> int:
    """Run ruff, writing captured output (and a JSON report) to /output.

    Not JUnit-shaped by design (per task scope) — just a clear pass/fail
    exit code plus readable output for a human or a non-blocking check
    per CLAUDE.md's COMPLETADO_PARCIALMENTE state.
    """
    report_path = OUTPUT / "lint.json"
    result = _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            str(WORKSPACE),
            "--output-format=json",
            f"--output-file={report_path}",
        ]
    )
    _write_log("lint", result)
    return result.returncode


CHECKS = {
    "install": check_install,
    "unit_tests": check_unit_tests,
    "lint": check_lint,
}


def main(argv: list[str]) -> int:
    import os

    OUTPUT.mkdir(parents=True, exist_ok=True)

    if len(argv) != 1:
        sys.stderr.write(
            f"usage: entrypoint.py <check>\nknown checks: {', '.join(KNOWN_CHECKS)}\n"
        )
        return 2

    name = argv[0]
    if name not in CHECKS:
        # Refuse anything not in the closed allowlist. This is the
        # concrete enforcement of "no free shell in the sandbox" — there
        # is no code path from an unrecognized argument to subprocess
        # execution.
        sys.stderr.write(
            f"unknown check '{name}'. known checks: {', '.join(KNOWN_CHECKS)}\n"
        )
        return 2

    workspace_get_url = os.environ.get(WORKSPACE_GET_URL_ENV)
    if workspace_get_url:
        try:
            fetch_workspace(workspace_get_url)
        except WorkspaceFetchError as exc:
            sys.stderr.write(f"workspace fetch failed: {exc}\n")
            return 2

    if not WORKSPACE.exists() or not any(WORKSPACE.iterdir()):
        sys.stderr.write(f"/workspace is missing or empty; nothing to check\n")
        return 2

    _emit("sandbox.check_started", check=name)
    exit_code = CHECKS[name]()
    # pytest's exit 5 is "no tests collected" -- a real, distinct outcome
    # from "tests failed", and the reason a repo with no suite reaches
    # BLOQUEADO rather than looking like a broken run.
    _emit("sandbox.check_finished", check=name, exit_code=exit_code)

    junit_put_url = os.environ.get(JUNIT_PUT_URL_ENV)
    if junit_put_url:
        try:
            push_junit(junit_put_url)
        except WorkspaceFetchError as exc:
            # The check itself already ran and produced a real result --
            # a failure to push it is reported, but must not overwrite a
            # genuine pass (0) with a misleading usage error (2), nor
            # hide a genuine failure (1) behind "looks fine, exit 0".
            sys.stderr.write(f"junit push failed: {exc}\n")
            return exit_code or 2

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
