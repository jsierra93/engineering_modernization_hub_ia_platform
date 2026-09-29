"""Deterministic checkpoints invoked by the state machine. Dispatches each action to the ledger or the verdict.
Never imports Bedrock (invariant 1).
"""

from __future__ import annotations

from typing import Any

from core_py.persistence import EventsTable, RunsTable

from core_ops.run_ledger import record_plan, record_spend, record_task_token, record_terminal_failure
from core_ops.verdict_service import compute_verdict
from core_ops.workspace_ops import prepare_sandbox, snapshot_workspace


class UnknownActionError(Exception):
    pass


_ACTIONS = {
    "record_plan": lambda event, runs, s3, events: record_plan(event, runs),
    "compute_verdict": lambda event, runs, s3, events: compute_verdict(event, runs, s3_resource=s3, events_table=events),
    "record_task_token": lambda event, runs, s3, events: record_task_token(event, runs),
    "record_terminal_failure": lambda event, runs, s3, events: record_terminal_failure(event, runs),
    "record_spend": lambda event, runs, s3, events: record_spend(event, runs, events),
    "snapshot_workspace": lambda event, runs, s3, events: snapshot_workspace(event, s3),
    "prepare_sandbox": lambda event, runs, s3, events: prepare_sandbox(event, s3),
}


def _run(
    event: dict[str, Any],
    *,
    runs_table: RunsTable,
    s3_resource: Any = None,
    events_table: EventsTable | None = None,
) -> dict[str, Any]:
    action = event["action"]
    if action not in _ACTIONS:
        raise UnknownActionError(f"action {action!r} is not implemented")
    return _ACTIONS[action](event, runs_table, s3_resource, events_table)


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    import boto3

    resource = boto3.resource("dynamodb")
    return _run(
        event,
        runs_table=RunsTable(resource=resource),
        s3_resource=boto3.resource("s3"),
        events_table=EventsTable(resource=resource),
    )
