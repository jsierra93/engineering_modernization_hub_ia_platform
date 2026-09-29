#!/usr/bin/env python3
"""Sandbox entrypoint: runs exactly one named check from the image's profile (/etc/modhub/profile.json), never a free command.
The profile is data baked into the image; only the platform ships it. No AWS SDK or credentials: workspace and JUnit travel over presigned URLs.
Exit codes: 0 passed, 1 check failed, 2 usage or transport error.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

WORKSPACE = Path("/workspace")
OUTPUT = Path("/output")

PROFILE_PATH = Path(os.environ.get("MODHUB_PROFILE_PATH", "/etc/modhub/profile.json"))

WORKSPACE_GET_URL_ENV = "WORKSPACE_GET_URL"
JUNIT_PUT_URL_ENV = "JUNIT_PUT_URL"

MAX_TOTAL_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 50 * 1024 * 1024


class WorkspaceFetchError(Exception):
    pass


# Duplicated from fetch_repo.sanitize on purpose: this image has no dependency on platform packages.
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

def _emit(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, default=str), flush=True)


def _write_log(name: str, result: subprocess.CompletedProcess) -> None:
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
    # Fixed argv, never a shell: the command is built entirely inside this file.
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _junit_summary(junit_path: Path) -> dict:
    if not junit_path.exists():
        return {"junit": "missing"}
    try:
        import xml.etree.ElementTree as ET

        root = ET.parse(junit_path).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        if suite is None:
            return {"junit": "no testsuite element"}
        return {
            "tests": suite.get("tests"),
            "failures": suite.get("failures"),
            "errors": suite.get("errors"),
            "skipped": suite.get("skipped"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"junit": f"unparseable: {exc}"}


def _expand(cmd: list[str], **values: str) -> list[str]:
    return [part.format(python=sys.executable, workspace=str(WORKSPACE), **values) for part in cmd]


def _prepare(name: str, group: dict) -> int:
    overall_rc = 0
    ran_any = False
    for step in group["steps"]:
        if "each_glob" in step:
            targets = [(path.name, str(path)) for path in sorted(WORKSPACE.glob(step["each_glob"]))]
        elif (WORKSPACE / step["when_exists"]).exists():
            targets = [("", "")]
        else:
            targets = []
        for file_name, file in targets:
            result = _run(_expand(step["cmd"], file=file))
            _write_log(step["log"].format(file_name=file_name), result)
            ran_any = True
            if result.returncode != 0:
                overall_rc = result.returncode
    if not ran_any:
        (OUTPUT / f"{name}.log").write_text(group["empty_note"], encoding="utf-8")
    return overall_rc


def run_check(profile: dict, name: str) -> int:
    spec = profile["checks"][name]
    if "prepare" in spec:
        prepare_rc = _prepare(spec["prepare"], profile["prepare"][spec["prepare"]])
        if prepare_rc != 0:
            _emit("sandbox.prepare_failed_before_check", check=name, exit_code=prepare_rc)
            return prepare_rc
    run = spec.get("run")
    if run is None:
        return 0

    junit_path = OUTPUT / "junit.xml"
    result = _run(_expand(run["cmd"], junit=str(junit_path), lint_report=str(OUTPUT / "lint.json")))
    _write_log(run["log"], result)
    if run.get("junit"):
        _emit("sandbox.junit_crosscheck", exit_code=result.returncode, **_junit_summary(junit_path))
        if not junit_path.exists():
            (OUTPUT / f"{run['log']}.error").write_text(
                f"{run['log']} did not produce /output/junit.xml -- see {run['log']}.log.\n", encoding="utf-8"
            )
            return result.returncode or 1
    return result.returncode


def load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    profile = load_profile()
    known = ", ".join(profile["checks"])

    if len(argv) != 1:
        sys.stderr.write(f"usage: entrypoint.py <check>\nknown checks: {known}\n")
        return 2

    name = argv[0]
    if name not in profile["checks"]:
        sys.stderr.write(f"unknown check '{name}'. known checks: {known}\n")
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
    exit_code = run_check(profile, name)
    _emit("sandbox.check_finished", check=name, exit_code=exit_code)

    junit_put_url = os.environ.get(JUNIT_PUT_URL_ENV)
    if junit_put_url:
        try:
            push_junit(junit_put_url)
        except WorkspaceFetchError as exc:
            sys.stderr.write(f"junit push failed: {exc}\n")
            return exit_code or 2

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
