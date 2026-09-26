#!/usr/bin/env python3
"""Sandbox entrypoint — runs exactly one named check.

CLAUDE.md invariant #3: "Checks are named, and their command comes from
the strategy. The agent chooses neither the command nor its flags. There
is no free shell in the sandbox." This script is the enforcement point
for that invariant at the container level: it accepts a single
positional argument — one of a small, hardcoded allowlist of check
names — and refuses anything else. There is no way to pass an arbitrary
command through this entrypoint.

I/O contract (the only interface this container has with the outside
world — no AWS SDK, no network calls other than package installation):
  /workspace  — the project to check (read/write; `install` writes
                packages here, `unit_tests`/`lint` write minor bytecode
                cache; the actual source is not modified by any check).
  /output     — where this script writes its results. Always written,
                whether the check passes or fails, so the caller can
                inspect what happened even after a non-zero exit.

Exit code contract:
  0   the check passed
  1   the check ran and failed (e.g. a test failed, lint found issues)
  2   usage/configuration error (unknown check name, missing workspace,
      etc.) — never confused with "the check ran and failed"
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WORKSPACE = Path("/workspace")
OUTPUT = Path("/output")

# The complete, closed set of checks this image will ever run. Adding a
# check means editing this file and rebuilding the image — it is never
# something a caller can inject at run time.
KNOWN_CHECKS = ("install", "unit_tests", "lint")


def _write_log(name: str, result: subprocess.CompletedProcess) -> None:
    """Persist stdout/stderr for a check under /output, always."""
    log_path = OUTPUT / f"{name}.log"
    log_path.write_text(
        f"$ {' '.join(result.args)}\n"
        f"exit_code={result.returncode}\n\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}\n",
        encoding="utf-8",
    )


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

    if not WORKSPACE.exists() or not any(WORKSPACE.iterdir()):
        sys.stderr.write(f"/workspace is missing or empty; nothing to check\n")
        return 2

    return CHECKS[name]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
