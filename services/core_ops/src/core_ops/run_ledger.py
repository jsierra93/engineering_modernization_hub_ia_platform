"""The run's ledger: records the plan, the task token, spend and terminal failures, and persists security denials.
Writes state only; it never decides an outcome (that is verdict_service).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core_py.models import Event, Run, RunStatus
from core_py.observability import log_event
from core_py.persistence import EventsTable, RunsTable

from core_ops.plan_hash import compute_plan_hash


def require_run(runs_table: RunsTable, run_id: Any) -> Run:
    run = runs_table.get(run_id)
    if run is None:
        raise ValueError(f"no such run: {run_id}")
    return run


def record_task_token(event: dict[str, Any], runs_table: RunsTable) -> dict[str, Any]:
    run_id = event["run_id"]
    run = require_run(runs_table, run_id)

    run.task_token = event["task_token"]
    runs_table.update_fields(run, "task_token")

    return {"run_id": str(run_id), "recorded": True}


def record_plan(event: dict[str, Any], runs_table: RunsTable) -> dict[str, Any]:
    run_id = event["run_id"]
    run = require_run(runs_table, run_id)

    plan_hash = compute_plan_hash(event["plan"])
    log_event("core_ops.plan_recorded", run_id=run_id, plan_hash=plan_hash)
    run.plan_hash = plan_hash
    run.plan = event["plan"]
    run.awaiting_approval_since = datetime.now(UTC)
    run.status = RunStatus.AWAITING_APPROVAL
    runs_table.update_fields(run, "plan_hash", "plan", "awaiting_approval_since", "status")

    return {"run_id": str(run_id), "plan_hash": plan_hash, "status": run.status.value}


def persist_denials(run_id: str, denials: list[dict[str, Any]], events_table: EventsTable | None) -> None:
    if not denials or events_table is None:
        return

    for denial in denials:
        events_table.append_next(
            Event(
                run_id=run_id,
                seq=0,
                type="SecurityBlocked",
                message=denial.get("reason"),
                data=denial,
            )
        )
        log_event("core_ops.security_blocked", run_id=run_id, **denial)


def record_spend(
    event: dict[str, Any], runs_table: RunsTable, events_table: EventsTable | None = None
) -> dict[str, Any]:
    run_id = event["run_id"]
    run = require_run(runs_table, run_id)

    persist_denials(run_id, event.get("denials") or [], events_table)

    phase, model_id = event.get("phase"), event.get("model_id")
    if phase and model_id and run.models_used.get(phase) != model_id:
        run.models_used[phase] = model_id
        runs_table.update_fields(run, "models_used")

    spent_usd = runs_table.add_spend(run_id, event["delta_usd"])
    exhausted = spent_usd >= run.max_usd
    elapsed_minutes = elapsed_working_minutes(run)
    time_exhausted = elapsed_minutes >= run.max_minutes
    budget_guard_stopped = bool(event.get("budget_stopped"))

    log_event(
        "core_ops.spend",
        run_id=run_id,
        delta_usd=event["delta_usd"],
        phase=phase,
        model_id=model_id,
        spent_usd=spent_usd,
        max_usd=run.max_usd,
        budget_exhausted=exhausted,
        elapsed_minutes=round(elapsed_minutes, 2),
        max_minutes=run.max_minutes,
        time_exhausted=time_exhausted,
        budget_guard_stopped=budget_guard_stopped,
    )
    return {
        "run_id": str(run_id),
        "spent_usd": spent_usd,
        "budget_exhausted": exhausted or budget_guard_stopped,
        "budget_guard_stopped": budget_guard_stopped,
        "time_exhausted": time_exhausted,
    }


def record_terminal_failure(event: dict[str, Any], runs_table: RunsTable) -> dict[str, Any]:
    run_id = event["run_id"]
    run = require_run(runs_table, run_id)

    run.status = RunStatus.FALLIDO_CONTROLADO
    runs_table.update_fields(run, "status")
    log_event("core_ops.terminal_failure", run_id=run_id, cause=str(event.get("cause"))[:300])
    return {"run_id": str(run_id), "status": run.status.value}


def elapsed_working_minutes(run: Run) -> float:
    return ((datetime.now(UTC) - run.created_at).total_seconds() - run.approval_wait_seconds) / 60.0

