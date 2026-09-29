"""The five-state verdict table, evaluated in fixed order; first match wins.
Pure and Bedrock-free (invariant 1); returns the state plus the reason code of the branch taken.
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

    budget_guard_stopped: bool = False
    baseline_failed: bool = False
    nothing_to_remediate: bool = False
    agent_concluded_infeasible: bool = False

    fix_iterations_exhausted_without_pass: bool = False
    unrecoverable_error: bool = False
    approval_timed_out: bool = False
    suite_violation: str | None = None

    checks: dict[str, bool] = field(default_factory=dict)
    blocking_checks: tuple[str, ...] = ("install", "unit_tests")

    diff_within_writable_paths: bool = True

    produced_changes: bool = True


def _blocking_checks_pass(inputs: VerdictInputs) -> bool:
    return all(inputs.checks.get(name, False) for name in inputs.blocking_checks)


def _all_checks_pass(inputs: VerdictInputs) -> bool:
    return len(inputs.checks) > 0 and all(inputs.checks.values())


# Order is the contract: first match wins. Weakening the suite outranks a merely failing fix loop.
def evaluate_verdict_with_reason(inputs: VerdictInputs) -> tuple[RunStatus, str]:
    if inputs.budget.spent_usd >= inputs.budget.max_usd:
        return RunStatus.PRESUPUESTO_AGOTADO, "BUDGET_USD_EXHAUSTED"
    if inputs.budget.elapsed_minutes >= inputs.budget.max_minutes:
        return RunStatus.PRESUPUESTO_AGOTADO, "TIME_EXHAUSTED"
    if inputs.budget_guard_stopped:
        return RunStatus.PRESUPUESTO_AGOTADO, "BUDGET_WORST_CASE"
    if (
        inputs.budget.iterations_used >= inputs.budget.max_iterations
        and not inputs.fix_iterations_exhausted_without_pass
        and not _blocking_checks_pass(inputs)
    ):
        return RunStatus.PRESUPUESTO_AGOTADO, "ITERATIONS_EXHAUSTED"

    if inputs.baseline_failed:
        return RunStatus.BLOQUEADO, "BASELINE_FAILING"
    if inputs.nothing_to_remediate:
        return RunStatus.BLOQUEADO, "NOTHING_TO_REMEDIATE"
    if inputs.agent_concluded_infeasible:
        return RunStatus.BLOQUEADO, "INFEASIBLE"

    if inputs.approval_timed_out:
        return RunStatus.FALLIDO_CONTROLADO, "APPROVAL_TIMED_OUT"
    if inputs.suite_violation in ("SUITE_SHRANK", "TESTS_SILENCED"):
        return RunStatus.FALLIDO_CONTROLADO, "SUITE_VIOLATION"
    if inputs.fix_iterations_exhausted_without_pass:
        return RunStatus.FALLIDO_CONTROLADO, "FIX_ITERATIONS_EXHAUSTED"
    if inputs.suite_violation is not None:
        return RunStatus.FALLIDO_CONTROLADO, "SUITE_VIOLATION"
    if inputs.unrecoverable_error:
        return RunStatus.FALLIDO_CONTROLADO, "UNRECOVERABLE_ERROR"
    if not inputs.produced_changes:
        return RunStatus.FALLIDO_CONTROLADO, "NO_CHANGES_PRODUCED"

    if not _blocking_checks_pass(inputs):
        return RunStatus.FALLIDO_CONTROLADO, "BLOCKING_CHECK_FAILED"

    if not inputs.diff_within_writable_paths:
        return RunStatus.FALLIDO_CONTROLADO, "SCOPE_ESCAPE"

    if _all_checks_pass(inputs):
        return RunStatus.LISTO_PARA_REVISION, "ALL_CHECKS_PASSED"

    return RunStatus.COMPLETADO_PARCIALMENTE, "NON_BLOCKING_CHECK_FAILED"
