"""POST /runs/{id}/approval: one conditional write records the decision, then the state machine resumes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

from core_py.identity import is_owner
from core_py.models import Run, RunStatus
from core_py.observability import log_event
from core_py.persistence import ApprovalConflictError, RunsTable

from api.access import caller_auth_is_recent, require_caller
from api.responses import Reject, ok_response, parse_json_body, path_run_id, public_run, returns_rejections


def _parse_decision(body: dict[str, Any], run_id: str) -> tuple[str, str]:
    decision = body.get("decision")
    plan_hash = body.get("plan_hash")
    if decision not in ("approve", "reject") or not plan_hash:
        raise Reject(422, "MISSING_FIELDS", "decision (approve|reject) and plan_hash are required.", run_id)
    return decision, plan_hash


def _authorize_approval(event: dict[str, Any], run: Run, run_id: str) -> str:
    sub = require_caller(event)
    if not is_owner(event, run.requested_by):
        raise Reject(403, "NOT_REQUESTER", "Only the user who requested this run may approve or reject it.", run_id)
    if not caller_auth_is_recent(event):
        raise Reject(401, "AUTH_NOT_RECENT", "Re-authenticate before approving or rejecting a run.", run_id)
    # Checked before the conditional write: without a token the callback cannot resume the execution.
    if not run.task_token:
        log_event("api.approval_without_token", run_id=run_id, status=run.status.value)
        raise Reject(409, "RUN_NOT_WAITING", "This run is not currently waiting for an approval callback.", run_id)
    return sub


def _record_decision(
    runs_table: RunsTable, run: Run, run_id: str, sub: str, plan_hash: str, decision: str, new_status: RunStatus
) -> None:
    try:
        runs_table.approve_or_reject(run_id, sub=sub, plan_hash=plan_hash, new_status=new_status.value)
    except ApprovalConflictError:
        raise Reject(
            409,
            "APPROVAL_CONFLICT",
            "This run is no longer AWAITING_APPROVAL with that plan_hash "
            "(it may have already been decided, or the plan changed).",
            run_id,
        ) from None

    if run.awaiting_approval_since is not None:
        waited = (datetime.now(UTC) - run.awaiting_approval_since).total_seconds()
        run.approval_wait_seconds += waited
        runs_table.update_fields(run, "approval_wait_seconds")
        log_event("api.approval_recorded", run_id=run_id, decision=decision, waited_seconds=round(waited, 1))


def _deliver_decision(
    sfn_client: Any, runs_table: RunsTable, run: Run, run_id: str, decision: str, plan_hash: str, body: dict[str, Any]
) -> None:
    try:
        if decision == "approve":
            sfn_client.send_task_success(
                taskToken=run.task_token,
                output=json.dumps({"approved": True, "plan_hash": plan_hash}),
            )
        else:
            sfn_client.send_task_failure(
                taskToken=run.task_token,
                error="ApprovalRejected",
                cause=body.get("reason") or "Rejected by requester.",
            )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        log_event("api.approval_callback_failed", run_id=run_id, error_code=code, error=str(exc)[:300])
        if code in ("TaskTimedOut", "TaskDoesNotExist"):
            raise Reject(
                409,
                "RUN_NO_LONGER_WAITING",
                "This run stopped waiting for approval before the decision reached it.",
                run_id,
            ) from None
        run.status = RunStatus.AWAITING_APPROVAL
        runs_table.update_fields(run, "status")
        raise Reject(
            503,
            "APPROVAL_CALLBACK_FAILED",
            "The decision was recorded but could not be delivered. Retry shortly.",
            run_id,
        ) from None


@returns_rejections
def handle_approval(event: dict[str, Any], runs_table: RunsTable, sfn_client: Any) -> dict[str, Any]:
    require_caller(event)
    run_id = path_run_id(event, require_uuid=True)
    body = parse_json_body(event, run_id)
    decision, plan_hash = _parse_decision(body, run_id)

    run = runs_table.get(run_id)
    if run is None:
        raise Reject(404, "RUN_NOT_FOUND", "No run with that id.", run_id)
    sub = _authorize_approval(event, run, run_id)

    new_status = RunStatus.RUNNING if decision == "approve" else RunStatus.CANCELADO
    _record_decision(runs_table, run, run_id, sub, plan_hash, decision, new_status)
    _deliver_decision(sfn_client, runs_table, run, run_id, decision, plan_hash, body)

    run.status = new_status
    return ok_response(200, public_run(run))
