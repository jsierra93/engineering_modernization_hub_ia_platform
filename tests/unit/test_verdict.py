"""Task 2.5: the five-state verdict table, evaluated in CLAUDE.md's fixed
order, first match wins. One fixture per triggering condition, plus an
explicit ordering test."""

from __future__ import annotations

from core_ops.verdict import BudgetStatus, VerdictInputs, evaluate_verdict
from core_py.models import RunStatus

HEALTHY_BUDGET = BudgetStatus(
    spent_usd=1.0,
    max_usd=5.0,
    elapsed_minutes=5.0,
    max_minutes=20.0,
    iterations_used=1,
    max_iterations=3,
)

EXHAUSTED_BUDGET = BudgetStatus(
    spent_usd=5.0,
    max_usd=5.0,
    elapsed_minutes=5.0,
    max_minutes=20.0,
    iterations_used=1,
    max_iterations=3,
)


def test_presupuesto_agotado_when_ledger_hits_max_usd():
    inputs = VerdictInputs(budget=EXHAUSTED_BUDGET)
    assert evaluate_verdict(inputs) == RunStatus.PRESUPUESTO_AGOTADO


def test_presupuesto_agotado_when_iterations_exhausted():
    budget = BudgetStatus(
        spent_usd=1.0, max_usd=5.0, elapsed_minutes=5.0, max_minutes=20.0,
        iterations_used=3, max_iterations=3,
    )
    inputs = VerdictInputs(budget=budget)
    assert evaluate_verdict(inputs) == RunStatus.PRESUPUESTO_AGOTADO


def test_bloqueado_when_baseline_already_fails():
    inputs = VerdictInputs(budget=HEALTHY_BUDGET, baseline_failed=True)
    assert evaluate_verdict(inputs) == RunStatus.BLOQUEADO


def test_bloqueado_when_agent_concludes_infeasible():
    inputs = VerdictInputs(budget=HEALTHY_BUDGET, agent_concluded_infeasible=True)
    assert evaluate_verdict(inputs) == RunStatus.BLOQUEADO


def test_fallido_controlado_when_fix_iterations_exhausted():
    inputs = VerdictInputs(
        budget=HEALTHY_BUDGET, fix_iterations_exhausted_without_pass=True
    )
    assert evaluate_verdict(inputs) == RunStatus.FALLIDO_CONTROLADO


def test_fallido_controlado_when_unrecoverable_error():
    inputs = VerdictInputs(budget=HEALTHY_BUDGET, unrecoverable_error=True)
    assert evaluate_verdict(inputs) == RunStatus.FALLIDO_CONTROLADO


def test_fallido_controlado_when_suite_violation_detected():
    inputs = VerdictInputs(budget=HEALTHY_BUDGET, suite_violation="SUITE_SHRANK")
    assert evaluate_verdict(inputs) == RunStatus.FALLIDO_CONTROLADO


def test_completado_parcialmente_when_lint_fails_but_blocking_checks_pass():
    inputs = VerdictInputs(
        budget=HEALTHY_BUDGET,
        checks={"install": True, "unit_tests": True, "lint": False},
    )
    assert evaluate_verdict(inputs) == RunStatus.COMPLETADO_PARCIALMENTE


def test_listo_para_revision_when_everything_passes_and_diff_contained():
    inputs = VerdictInputs(
        budget=HEALTHY_BUDGET,
        checks={"install": True, "unit_tests": True, "lint": True},
        diff_within_writable_paths=True,
    )
    assert evaluate_verdict(inputs) == RunStatus.LISTO_PARA_REVISION


def test_ordering_budget_exhausted_wins_over_suite_violation():
    """A run that is BOTH over budget AND has a suite violation must
    resolve to PRESUPUESTO_AGOTADO, since it is checked first."""
    inputs = VerdictInputs(
        budget=EXHAUSTED_BUDGET,
        suite_violation="SUITE_SHRANK",
        baseline_failed=True,
        fix_iterations_exhausted_without_pass=True,
    )
    assert evaluate_verdict(inputs) == RunStatus.PRESUPUESTO_AGOTADO


def test_ordering_bloqueado_wins_over_fallido_controlado():
    inputs = VerdictInputs(
        budget=HEALTHY_BUDGET,
        baseline_failed=True,
        suite_violation="SUITE_SHRANK",
    )
    assert evaluate_verdict(inputs) == RunStatus.BLOQUEADO


def test_diff_outside_writable_paths_is_never_listo():
    inputs = VerdictInputs(
        budget=HEALTHY_BUDGET,
        checks={"install": True, "unit_tests": True, "lint": True},
        diff_within_writable_paths=False,
    )
    assert evaluate_verdict(inputs) == RunStatus.FALLIDO_CONTROLADO
