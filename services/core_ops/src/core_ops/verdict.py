"""PLAN.md task 2.5 -- the five-state verdict table (CLAUDE.md's "The
five final states"). `core_ops` evaluates in this exact order, first
match wins. Never let the model propose one -- this module never imports
a Bedrock client, never references a model ID, and never imports anything
from `core_py.bedrock_models` (CLAUDE.md invariant #1).

The verdict depends only on: the budget ledger, a small set of booleans
the orchestrator/state-machine sets from real signals (baseline result,
an explicit infeasibility conclusion the agent must substantiate with
evidence -- persisted, never inferred, per invariant #11 -- fix-loop
exhaustion, unrecoverable tool/model errors), the named checks' pass/fail
results, the 2.4 suite-integrity verdict, and whether the diff stayed
inside the strategy's writable paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core_py.models import RunStatus


@dataclass(frozen=True)
class BudgetStatus:
    spent_usd: float
    max_usd: float
    elapsed_minutes: float
    max_minutes: float
    iterations_used: int
    max_iterations: int

    def exhausted(self) -> bool:
        return (
            self.spent_usd >= self.max_usd
            or self.elapsed_minutes >= self.max_minutes
            or self.iterations_used >= self.max_iterations
        )


@dataclass(frozen=True)
class VerdictInputs:
    budget: BudgetStatus

    # 2. BLOQUEADO
    baseline_failed: bool = False
    agent_concluded_infeasible: bool = False

    # 3. FALLIDO_CONTROLADO
    fix_iterations_exhausted_without_pass: bool = False
    unrecoverable_error: bool = False
    suite_violation: str | None = None

    # 4/5: named checks, e.g. {"install": True, "unit_tests": True, "lint": False}.
    checks: dict[str, bool] = field(default_factory=dict)
    blocking_checks: tuple[str, ...] = ("install", "unit_tests")

    # 5. LISTO_PARA_REVISION
    diff_within_writable_paths: bool = True


def _blocking_checks_pass(inputs: VerdictInputs) -> bool:
    return all(inputs.checks.get(name, False) for name in inputs.blocking_checks)


def _all_checks_pass(inputs: VerdictInputs) -> bool:
    return len(inputs.checks) > 0 and all(inputs.checks.values())


def evaluate_verdict(inputs: VerdictInputs) -> RunStatus:
    """Evaluate the five final states in CLAUDE.md's fixed order, first
    match wins."""

    # 1. PRESUPUESTO_AGOTADO
    if inputs.budget.exhausted():
        return RunStatus.PRESUPUESTO_AGOTADO

    # 2. BLOQUEADO
    if inputs.baseline_failed or inputs.agent_concluded_infeasible:
        return RunStatus.BLOQUEADO

    # 3. FALLIDO_CONTROLADO
    if (
        inputs.fix_iterations_exhausted_without_pass
        or inputs.unrecoverable_error
        or inputs.suite_violation is not None
    ):
        return RunStatus.FALLIDO_CONTROLADO

    # A blocking check (install/unit_tests) failing without any of the
    # above flags set is still a controlled failure -- there is no path
    # to COMPLETADO_PARCIALMENTE or LISTO_PARA_REVISION without them.
    if not _blocking_checks_pass(inputs):
        return RunStatus.FALLIDO_CONTROLADO

    # A diff that escaped the approved writable_paths is a scope
    # violation, not a clean delivery -- never LISTO_PARA_REVISION.
    if not inputs.diff_within_writable_paths:
        return RunStatus.FALLIDO_CONTROLADO

    # 5. LISTO_PARA_REVISION -- every check passes, suite intact, diff contained.
    if _all_checks_pass(inputs):
        return RunStatus.LISTO_PARA_REVISION

    # 4. COMPLETADO_PARCIALMENTE -- blocking checks pass, suite intact,
    # but some non-blocking check (e.g. lint) failed.
    return RunStatus.COMPLETADO_PARCIALMENTE
