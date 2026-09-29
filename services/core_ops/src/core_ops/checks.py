"""Derives the named check results from the sandbox evidence the state machine forwards.
The state machine passes what it observed (container exit code or ECS error); it never declares a pass.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from core_py.models import CheckSpec

FALLBACK_CHECKS = (CheckSpec(name="unit_tests"), CheckSpec(name="lint", blocking=False))


def _exit_code(evidence: dict[str, Any] | None) -> int | None:
    if not evidence:
        return None
    if "exit_code" in evidence:
        code = evidence["exit_code"]
        return code if isinstance(code, int) else None
    error = evidence.get("error") or {}
    if error.get("Error") != "States.TaskFailed":
        return None
    try:
        code = json.loads(error.get("Cause") or "")["Containers"][0]["ExitCode"]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return code if isinstance(code, int) else None


def check_passed(evidence: dict[str, Any] | None) -> bool | None:
    code = _exit_code(evidence)
    return None if code is None else code == 0


def blocking_names(specs: Iterable[CheckSpec]) -> tuple[str, ...]:
    return tuple(spec.name for spec in specs if spec.blocking)


def checks_from_evidence(
    evidence: dict[str, Any], specs: Iterable[CheckSpec], baseline_clean: dict[str, bool] | None
) -> dict[str, bool]:
    baseline_clean = baseline_clean or {}
    checks: dict[str, bool] = {}
    for spec in specs:
        passed = check_passed(evidence.get(spec.name)) is True
        if spec.blocking:
            checks[spec.name] = passed
        elif spec.name in evidence:
            if passed:
                checks[spec.name] = True
            elif baseline_clean.get(spec.name):
                checks[spec.name] = False
    return checks
