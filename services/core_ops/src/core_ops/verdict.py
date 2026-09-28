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
    approval_timed_out: bool = False
    suite_violation: str | None = None

    # 4/5: named checks, e.g. {"install": True, "unit_tests": True, "lint": False}.
    checks: dict[str, bool] = field(default_factory=dict)
    blocking_checks: tuple[str, ...] = ("install", "unit_tests")

    # 5. LISTO_PARA_REVISION
    diff_within_writable_paths: bool = True

    # A run that modernized nothing is not a delivery. The suite stays
    # green because the baseline was green, so every check-based signal
    # reads as success -- only the empty diff distinguishes "nothing
    # needed changing" from "the agent never wrote anything".
    produced_changes: bool = True


def _blocking_checks_pass(inputs: VerdictInputs) -> bool:
    return all(inputs.checks.get(name, False) for name in inputs.blocking_checks)


def _all_checks_pass(inputs: VerdictInputs) -> bool:
    return len(inputs.checks) > 0 and all(inputs.checks.values())


def evaluate_verdict(inputs: VerdictInputs) -> RunStatus:
    """The state alone, for callers that only need the verdict."""

    return evaluate_verdict_with_reason(inputs)[0]


def evaluate_verdict_with_reason(inputs: VerdictInputs) -> tuple[RunStatus, str]:
    """Evaluate the five final states in CLAUDE.md's fixed order, first
    match wins, and report which branch matched.

    The five names come from the brief verbatim and none of them may be
    split. But a state answers "what happened", not "why": one
    FALLIDO_CONTROLADO covers six different conditions, from an exhausted
    fix loop to a deliberately weakened test suite -- and a reader cannot
    tell a platform failure from a security event by the state alone. The
    reason code is the branch this function actually took, so the report
    can say which, without inventing a sixth state the brief never listed.
    """

    # 1. PRESUPUESTO_AGOTADO
    if inputs.budget.spent_usd >= inputs.budget.max_usd:
        return RunStatus.PRESUPUESTO_AGOTADO, "BUDGET_USD_EXHAUSTED"
    if inputs.budget.elapsed_minutes >= inputs.budget.max_minutes:
        return RunStatus.PRESUPUESTO_AGOTADO, "TIME_EXHAUSTED"
    # Iterations are the one limit that can run out and still reach a
    # verdict: the fix loop exhausting is FALLIDO_CONTROLADO with its own
    # reason, and a run whose checks pass on its *last* iteration succeeded
    # -- spending the whole allowance is not the same as running out of it.
    # CLAUDE.md scopes PRESUPUESTO_AGOTADO to a limit hit "before a
    # verdict"; both of those reached one.
    if (
        inputs.budget.iterations_used >= inputs.budget.max_iterations
        and not inputs.fix_iterations_exhausted_without_pass
        and not _blocking_checks_pass(inputs)
    ):
        return RunStatus.PRESUPUESTO_AGOTADO, "ITERATIONS_EXHAUSTED"

    # 2. BLOQUEADO -- two situations a reader must not confuse: a repo that
    # was already broken before the platform touched it, and a reasoned
    # conclusion that the modernization cannot be done.
    if inputs.baseline_failed:
        return RunStatus.BLOQUEADO, "BASELINE_FAILING"
    if inputs.agent_concluded_infeasible:
        return RunStatus.BLOQUEADO, "INFEASIBLE"

    # 3. FALLIDO_CONTROLADO
    #
    # Nobody approved within the window. It is not CANCELADO -- that is an
    # explicit human decision and here nobody decided anything -- and it is
    # not PRESUPUESTO_AGOTADO, because approval wait is deliberately
    # excluded from max_minutes (that limit bounds the work, not the
    # deliberation). The run stopped cleanly having delivered nothing.
    if inputs.approval_timed_out:
        return RunStatus.FALLIDO_CONTROLADO, "APPROVAL_TIMED_OUT"
    #
    # Deleting or silencing tests is something the agent *did*, and it is a
    # security event whatever else happened -- it wins outright. A dropped
    # passed count is different: it also describes a fix loop that ran out
    # of attempts, which is not tampering. Reporting that as SUITE_VIOLATION
    # accuses the agent of weakening a suite it never touched; the verdict
    # is FALLIDO_CONTROLADO either way, but only one of the two reasons is
    # true.
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

    # A blocking check (install/unit_tests) failing without any of the
    # above flags set is still a controlled failure -- there is no path
    # to COMPLETADO_PARCIALMENTE or LISTO_PARA_REVISION without them.
    if not _blocking_checks_pass(inputs):
        return RunStatus.FALLIDO_CONTROLADO, "BLOCKING_CHECK_FAILED"

    # A diff that escaped the approved writable_paths is a scope
    # violation, not a clean delivery -- never LISTO_PARA_REVISION.
    if not inputs.diff_within_writable_paths:
        return RunStatus.FALLIDO_CONTROLADO, "SCOPE_ESCAPE"

    # 5. LISTO_PARA_REVISION -- every check passes, suite intact, diff contained.
    if _all_checks_pass(inputs):
        return RunStatus.LISTO_PARA_REVISION, "ALL_CHECKS_PASSED"

    # 4. COMPLETADO_PARCIALMENTE -- blocking checks pass, suite intact,
    # but some non-blocking check (e.g. lint) failed.
    return RunStatus.COMPLETADO_PARCIALMENTE, "NON_BLOCKING_CHECK_FAILED"
