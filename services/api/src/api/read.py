"""Read-only routes: the requester's own runs, one run and its report."""

from __future__ import annotations

import os
from typing import Any

from core_py.constants import WORKSPACE_BUCKET_ENV
from core_py.models import Run
from core_py.observability import log_event
from core_py.persistence import EventsTable, RunsTable

from api.access import load_own_run, require_caller
from api.responses import ok_response, path_run_id, public_run, returns_rejections


SECURITY_EVENT_TYPES = ("SecurityBlocked",)


@returns_rejections
def list_runs(event: dict[str, Any], runs_table: RunsTable) -> dict[str, Any]:
    status = (event.get("queryStringParameters") or {}).get("status")
    runs = runs_table.query_by_requested_by(require_caller(event))
    if status:
        runs = [run for run in runs if run.status.value == status]
    runs.sort(key=lambda run: run.created_at, reverse=True)
    return ok_response(200, {"items": [public_run(run) for run in runs]})


def _security_events(run_id: str, events_table: EventsTable | None) -> list[dict[str, Any]]:
    if events_table is None:
        return []
    try:
        return [
            {"type": e.type, "message": e.message, "data": e.data}
            for e in events_table.query_by_run_id(run_id)
            if e.type in SECURITY_EVENT_TYPES
        ]
    except Exception as exc:  # noqa: BLE001 - evidence, never a verdict input
        log_event("api.events_read_failed", run_id=run_id, error=str(exc)[:200])
        return []


def _read_diff(run: Run, s3_resource: Any) -> str | None:
    bucket = os.environ.get(WORKSPACE_BUCKET_ENV)
    if not run.diff_key or not bucket or s3_resource is None:
        return None
    try:
        return s3_resource.Object(bucket, run.diff_key).get()["Body"].read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        log_event("api.diff_read_failed", run_id=str(run.run_id), key=run.diff_key, error=str(exc)[:200])
        return None


@returns_rejections
def get_report(
    event: dict[str, Any],
    runs_table: RunsTable,
    s3_resource: Any = None,
    events_table: EventsTable | None = None,
) -> dict[str, Any]:
    run_id = path_run_id(event, require_uuid=False)
    run = load_own_run(event, runs_table, run_id)

    plan = run.plan or {}
    return ok_response(
        200,
        {
            "run_id": str(run.run_id),
            "status": run.status.value,
            "repo": run.repo,
            "commit": run.commit,
            "objetivo": run.objetivo,
            "strategy": {"id": run.strategy_id, "version": run.strategy_version},
            "verdict": {
                "status": run.status.value,
                "spent_usd": run.spent_usd,
                "max_usd": run.max_usd,
                "iterations_used": run.iterations_used,
                "max_iterations": run.max_iterations,
            },
            "narrative": {
                "summary": plan.get("summary"),
                "viability_reason": plan.get("viability_reason"),
                "sources": plan.get("sources", []),
                "risks": plan.get("risks", []),
            },
            "reason_code": run.reason_code,
            "security_events": _security_events(run_id, events_table),
            "changed_paths": run.changed_paths,
            "pull_request_url": run.pull_request_url,
            "diff": _read_diff(run, s3_resource),
            "models_used": run.models_used,
            "plan_hash": run.plan_hash,
            "created_at": run.created_at,
        },
    )


@returns_rejections
def get_run(event: dict[str, Any], runs_table: RunsTable) -> dict[str, Any]:
    run_id = path_run_id(event, require_uuid=True)
    return ok_response(200, public_run(load_own_run(event, runs_table, run_id)))
