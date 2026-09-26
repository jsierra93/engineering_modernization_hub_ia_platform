"""Closes the gap flagged while wiring Fase 3's ASL: core_ops had real
verdict/plan_hash/limits logic (Fase 2) but no Lambda handler dispatching
it. These tests prove the two real checkpoints -- record_plan (right
after DiscoveryPlan) and compute_verdict (after Baseline/Verify) -- both
persist to a real (moto-mocked) DynamoDB table, matching how core_ops
actually runs in production."""

from __future__ import annotations

import boto3
import pytest
from core_py.models import Restricciones, Run, RunStatus
from core_py.persistence import RunsTable, create_tables
from moto import mock_aws

from core_ops.handler import UnknownActionError, _run
from core_ops.plan_hash import compute_plan_hash

RUN_ID = "11111111-1111-1111-1111-111111111111"
COMMIT = "a" * 40


@pytest.fixture()
def runs_table():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        create_tables(resource)
        table = RunsTable(resource=resource)
        run = Run(
            run_id=RUN_ID,
            repo="octocat/Hello-World",
            commit=COMMIT,
            objetivo="migrar pydantic v1 a v2",
            restricciones=Restricciones(),
            requested_by="user-1",
            strategy_id="python-pydantic-v2",
            strategy_version="1.0.0",
            max_usd=2.0,
            max_iterations=3,
            max_minutes=20,
        )
        table.put(run)
        yield table


def test_record_task_token_persists_it_on_the_run(runs_table):
    """Fase 4 (4.3): AwaitApproval invokes this so a much later, separate
    Lambda invocation (POST /runs/{id}/approval) can retrieve the token
    and call SendTaskSuccess/Failure."""

    result = _run(
        {"action": "record_task_token", "run_id": RUN_ID, "task_token": "AAAA-fake-task-token-BBBB"},
        runs_table=runs_table,
    )

    assert result["recorded"] is True
    stored = runs_table.get(RUN_ID)
    assert stored.task_token == "AAAA-fake-task-token-BBBB"


def test_record_plan_sets_status_and_a_deterministic_hash(runs_table):
    plan = {"summary": "Migrate models", "planned_changes": [{"path": "src/models.py", "reason": "x"}]}

    result = _run({"action": "record_plan", "run_id": RUN_ID, "plan": plan}, runs_table=runs_table)

    assert result["plan_hash"] == compute_plan_hash(plan)
    assert result["status"] == "AWAITING_APPROVAL"
    stored = runs_table.get(RUN_ID)
    assert stored.plan_hash == result["plan_hash"]
    assert stored.status == RunStatus.AWAITING_APPROVAL


def test_record_plan_hash_is_insensitive_to_key_order(runs_table):
    """The model/framework serializing a dict with a different key order
    must not change the hash the approval endpoint later checks against."""
    plan_a = {"summary": "x", "planned_changes": []}
    plan_b = {"planned_changes": [], "summary": "x"}

    result_a = _run({"action": "record_plan", "run_id": RUN_ID, "plan": plan_a}, runs_table=runs_table)
    result_b = _run({"action": "record_plan", "run_id": RUN_ID, "plan": plan_b}, runs_table=runs_table)

    assert result_a["plan_hash"] == result_b["plan_hash"]


_PASSING_JUNIT = '<testsuites><testsuite tests="3"><testcase name="a"/><testcase name="b"/><testcase name="c"/></testsuite></testsuites>'
_FAILING_JUNIT = '<testsuites><testsuite tests="3"><testcase name="a"><failure/></testcase><testcase name="b"/><testcase name="c"/></testsuite></testsuites>'
_SHRUNK_JUNIT = '<testsuites><testsuite tests="1"><testcase name="a"/></testsuite></testsuites>'


def test_compute_verdict_listo_para_revision_when_everything_passes(runs_table):
    result = _run(
        {
            "action": "compute_verdict",
            "run_id": RUN_ID,
            "baseline_junit_xml": _PASSING_JUNIT,
            "final_junit_xml": _PASSING_JUNIT,
            "checks": {"install": True, "unit_tests": True, "lint": True},
        },
        runs_table=runs_table,
    )

    assert result["status"] == "LISTO_PARA_REVISION"
    assert runs_table.get(RUN_ID).status == RunStatus.LISTO_PARA_REVISION


def test_compute_verdict_fallido_controlado_on_suite_shrinkage(runs_table):
    result = _run(
        {
            "action": "compute_verdict",
            "run_id": RUN_ID,
            "baseline_junit_xml": _PASSING_JUNIT,
            "final_junit_xml": _SHRUNK_JUNIT,
            "checks": {"install": True, "unit_tests": True},
        },
        runs_table=runs_table,
    )

    assert result["status"] == "FALLIDO_CONTROLADO"
    assert result["suite_violation"] == "SUITE_SHRANK"


def test_compute_verdict_completado_parcialmente_when_only_lint_fails(runs_table):
    result = _run(
        {
            "action": "compute_verdict",
            "run_id": RUN_ID,
            "baseline_junit_xml": _PASSING_JUNIT,
            "final_junit_xml": _PASSING_JUNIT,
            "checks": {"install": True, "unit_tests": True, "lint": False},
        },
        runs_table=runs_table,
    )

    assert result["status"] == "COMPLETADO_PARCIALMENTE"


def test_compute_verdict_presupuesto_agotado_takes_priority_over_suite_violation(runs_table):
    """Confirms the handler wires BudgetStatus from the real Run record --
    a run already over budget must resolve to PRESUPUESTO_AGOTADO even
    with a suite violation also present (CLAUDE.md's fixed evaluation
    order, exercised through the real handler, not just evaluate_verdict
    directly)."""
    run = runs_table.get(RUN_ID)
    run.spent_usd = run.max_usd  # exhausted
    runs_table.put(run)

    result = _run(
        {
            "action": "compute_verdict",
            "run_id": RUN_ID,
            "baseline_junit_xml": _PASSING_JUNIT,
            "final_junit_xml": _SHRUNK_JUNIT,
            "checks": {"install": True, "unit_tests": True},
        },
        runs_table=runs_table,
    )

    assert result["status"] == "PRESUPUESTO_AGOTADO"


def test_unknown_action_raises_loudly(runs_table):
    with pytest.raises(UnknownActionError):
        _run({"action": "not_a_real_action", "run_id": RUN_ID}, runs_table=runs_table)


def test_unknown_run_raises_loudly(runs_table):
    with pytest.raises(ValueError, match="no such run"):
        _run({"action": "record_plan", "run_id": "99999999-9999-9999-9999-999999999999", "plan": {}}, runs_table=runs_table)
