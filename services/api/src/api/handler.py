"""lambda api handler: creates, lists, reads and approves runs, and serves the report.
Does not call Bedrock directly; objective resolution lives in api/resolver.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
import uuid
from typing import Any

import boto3

from botocore.exceptions import ClientError
from pydantic import ValidationError

from core_py.constants import WORKSPACE_BUCKET_ENV
from core_py.limits import LIMIT_FIELDS, LimitsConfigurationError, LimitsRequestError, platform_ceiling, resolve_limits
from core_py.models import Restricciones, Run, RunStatus
from core_py.observability import log_event
from core_py.persistence import ApprovalConflictError, EventsTable, RunsTable

from api.resolver import NoStrategyMatchError, ResolverUnavailableError, resolve_strategy
from api.strategy_lookup import list_strategy_manifests

STATE_MACHINE_ARN_ENV = "MODHUB_STATE_MACHINE_ARN"

APPROVAL_MAX_AUTH_AGE_SECONDS_ENV = "MODHUB_APPROVAL_MAX_AUTH_AGE_SECONDS"

DEV_STRATEGY_ID_ENV = "MODHUB_DEV_STRATEGY_ID"

REPO_ALLOWLIST_ENV = "MODHUB_REPO_ALLOWLIST"
DEFAULT_APPROVAL_MAX_AUTH_AGE_SECONDS = 300



def _repo_is_allowed(repo: str, allowlist: list[str]) -> bool:
    owner = repo.split("/", 1)[0]
    return repo in allowlist or f"{owner}/*" in allowlist


def _loggable_body(event: dict[str, Any]) -> Any:
    raw = event.get("body") or ""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw[:2000]


def _error_response(status_code: int, code: str, message: str, run_id: str | None) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"code": code, "message": message, "run_id": run_id}),
    }


def _ok_response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    }


def _requested_by(event: dict[str, Any]) -> str:
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    if claims.get("sub"):
        return claims["sub"]
    headers = event.get("headers") or {}
    return headers.get("x-requested-by") or headers.get("X-Requested-By") or "anonymous"


def _load_own_run(event: dict[str, Any], runs_table: RunsTable, run_id: str):
    run = runs_table.get(run_id)
    # Someone else's run answers 404, not 403, so a guessed run_id confirms nothing.
    if run is None or run.requested_by != _requested_by(event):
        return None, _error_response(404, "RUN_NOT_FOUND", "No run with that id.", run_id)
    return run, None


def _get_trace_id(event: dict[str, Any]) -> str:
    headers = event.get("headers") or {}
    return headers.get("x-trace-id") or headers.get("X-Trace-Id") or str(uuid.uuid4())


def _auth_is_recent(event: dict[str, Any]) -> bool:
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    auth_time = claims.get("auth_time")
    if auth_time is None:
        return True

    max_age_seconds = int(
        os.environ.get(APPROVAL_MAX_AUTH_AGE_SECONDS_ENV, DEFAULT_APPROVAL_MAX_AUTH_AGE_SECONDS)
    )
    return (time.time() - int(auth_time)) <= max_age_seconds


def create_run(
    event: dict[str, Any],
    runs_table: RunsTable,
    sfn_client: Any,
    bedrock_client: Any = None,
) -> dict[str, Any]:
    trace_id = _get_trace_id(event)

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _error_response(400, "INVALID_BODY", "Request body is not valid JSON.", None)

    required = ["repo", "commit", "objetivo", "max_usd", "max_iterations", "max_minutes"]
    missing = [field for field in required if field not in body]
    if missing:
        return _error_response(
            422,
            "MISSING_FIELDS",
            f"Missing required fields: {', '.join(missing)}",
            None,
        )

    requested_by = _requested_by(event)

    allowlist = [entry.strip() for entry in os.environ.get(REPO_ALLOWLIST_ENV, "").split(",") if entry.strip()]
    if allowlist and not _repo_is_allowed(str(body.get("repo", "")), allowlist):
        return _error_response(
            403,
            "REPO_NOT_ALLOWED",
            f"{body.get('repo')!r} is not on this deployment's repository allowlist.",
            None,
        )

    candidates = list_strategy_manifests()
    dev_strategy_id = os.environ.get(DEV_STRATEGY_ID_ENV)
    if dev_strategy_id:
        manifest = next((m for m in candidates if m.id == dev_strategy_id), None)
        if manifest is None:
            return _error_response(
                500,
                "DEV_STRATEGY_MISCONFIGURED",
                f"{DEV_STRATEGY_ID_ENV}={dev_strategy_id!r} does not match any registered strategy.",
                None,
            )
        match_confidence = 1.0
    else:
        try:
            manifest, match_confidence = resolve_strategy(
                body["objetivo"], candidates, bedrock_client=bedrock_client
            )
        except NoStrategyMatchError as exc:
            return _error_response(422, "NO_STRATEGY_MATCH", str(exc), None)
        except ResolverUnavailableError as exc:
            log_event("api.resolver_unavailable", trace_id=trace_id, error=str(exc)[:300])
            return _error_response(
                503,
                "RESOLVER_UNAVAILABLE",
                "The objective could not be resolved right now. Retry shortly.",
                None,
            )

    for field in LIMIT_FIELDS:
        value = body[field]
        # bool is an int subclass, so it must be rejected explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return _error_response(
                422,
                "INVALID_LIMIT",
                f"{field} must be a number, got {type(value).__name__}.",
                None,
            )
        if value <= 0:
            return _error_response(
                422, "INVALID_LIMIT", f"{field} must be greater than zero.", None
            )

    try:
        resolve_limits({field: body[field] for field in LIMIT_FIELDS}, manifest.limits, platform_ceiling().as_dict())
    except LimitsRequestError as exc:
        return _error_response(
            422,
            "LIMIT_EXCEEDS_STRATEGY_MAX",
            f"requested {exc.field}={exc.requested} exceeds strategy {manifest.id}'s max of {exc.maximum}.",
            None,
        )
    except LimitsConfigurationError as exc:
        log_event("api.strategy_limits_misconfigured", strategy_id=manifest.id, error=str(exc)[:300], trace_id=trace_id)
        return _error_response(500, "STRATEGY_MISCONFIGURED", "The resolved strategy declares limits above the platform ceiling.", None)

    try:
        run = Run(
            repo=body["repo"],
            commit=body["commit"],
            objetivo=body["objetivo"],
            inputs=body.get("inputs", {}),
            restricciones=Restricciones(**body.get("restricciones", {})),
            requested_by=requested_by,
            strategy_id=manifest.id,
            strategy_version=manifest.version,
            max_usd=body["max_usd"],
            max_iterations=body["max_iterations"],
            max_minutes=body["max_minutes"],
            status=RunStatus.PENDING,
        )
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        log_event("api.invalid_request", trace_id=trace_id, problems=problems)
        return _error_response(422, "INVALID_REQUEST", problems, None)

    runs_table.put(run)
    log_event(
        "api.run_created",
        run_id=run.run_id,
        trace_id=trace_id,
        strategy_id=manifest.id,
        match_confidence=match_confidence,
        requested_by=requested_by,
        max_usd=run.max_usd,
        max_iterations=run.max_iterations,
        max_minutes=run.max_minutes,
    )

    state_machine_arn = os.environ.get(STATE_MACHINE_ARN_ENV, "arn:aws:states:local:000000000000:stateMachine:modhub-stub")
    sfn_client.start_execution(
        stateMachineArn=state_machine_arn,
        name=str(run.run_id),
        input=json.dumps(
            {
                "trace_id": trace_id,
                "run_id": str(run.run_id),
                "repo": run.repo,
                "commit": run.commit,
                "objetivo": run.objetivo,
                "strategy_id": run.strategy_id,
                "max_iterations": run.max_iterations,
                "excluded_paths": run.restricciones.excluded_paths,
                "iteration": 0,
            }
        ),
    )

    return _ok_response(
        201,
        {
            "run_id": str(run.run_id),
            "status": run.status.value,
            "resolved_strategy": {
                "id": run.strategy_id,
                "version": run.strategy_version,
                "match_confidence": match_confidence,
            },
            "requested_by": run.requested_by,
            "created_at": run.created_at.isoformat(),
        },
    )


def list_runs(
    event: dict[str, Any],
    runs_table: RunsTable,
) -> dict[str, Any]:
    query_params = event.get("queryStringParameters") or {}
    status = query_params.get("status")
    sub = _requested_by(event)

    runs = runs_table.query_by_requested_by(sub)
    if status:
        runs = [run for run in runs if run.status.value == status]

    runs.sort(key=lambda run: run.created_at, reverse=True)
    return _ok_response(
        200,
        {"items": [run.model_dump(mode="json", exclude={"task_token"}) for run in runs]},
    )


SECURITY_EVENT_TYPES = ("SecurityBlocked",)


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


def get_report(
    event: dict[str, Any],
    runs_table: RunsTable,
    s3_resource: Any = None,
    events_table: EventsTable | None = None,
) -> dict[str, Any]:
    path_params = event.get("pathParameters") or {}
    run_id = path_params.get("run_id")
    if not run_id:
        return _error_response(400, "MISSING_RUN_ID", "run_id path parameter is required.", None)

    run, denied = _load_own_run(event, runs_table, run_id)
    if denied:
        return denied

    plan = run.plan or {}
    return _ok_response(
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


def get_run(
    event: dict[str, Any],
    runs_table: RunsTable,
) -> dict[str, Any]:
    path_params = event.get("pathParameters") or {}
    run_id = path_params.get("run_id")
    if not run_id:
        return _error_response(400, "MISSING_RUN_ID", "run_id path parameter is required.", None)

    try:
        uuid.UUID(run_id)
    except ValueError:
        return _error_response(400, "INVALID_RUN_ID", "run_id must be a UUID.", run_id)

    run, denied = _load_own_run(event, runs_table, run_id)
    if denied:
        return denied

    return _ok_response(200, run.model_dump(mode="json", exclude={"task_token"}))


def handle_approval(
    event: dict[str, Any],
    runs_table: RunsTable,
    sfn_client: Any,
) -> dict[str, Any]:
    path_params = event.get("pathParameters") or {}
    run_id = path_params.get("run_id")
    if not run_id:
        return _error_response(400, "MISSING_RUN_ID", "run_id path parameter is required.", None)

    try:
        uuid.UUID(run_id)
    except ValueError:
        return _error_response(400, "INVALID_RUN_ID", "run_id must be a UUID.", run_id)

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _error_response(400, "INVALID_BODY", "Request body is not valid JSON.", run_id)

    decision = body.get("decision")
    plan_hash = body.get("plan_hash")
    if decision not in ("approve", "reject") or not plan_hash:
        return _error_response(
            422,
            "MISSING_FIELDS",
            "decision (approve|reject) and plan_hash are required.",
            run_id,
        )

    run = runs_table.get(run_id)
    if run is None:
        return _error_response(404, "RUN_NOT_FOUND", "No run with that id.", run_id)

    sub = _requested_by(event)
    if sub != run.requested_by:
        return _error_response(
            403,
            "NOT_REQUESTER",
            "Only the user who requested this run may approve or reject it.",
            run_id,
        )

    if not _auth_is_recent(event):
        return _error_response(
            401,
            "AUTH_NOT_RECENT",
            "Re-authenticate before approving or rejecting a run.",
            run_id,
        )

    # Checked before the conditional write: without a token the callback cannot resume the execution.
    if not run.task_token:
        log_event("api.approval_without_token", run_id=run_id, status=run.status.value)
        return _error_response(
            409,
            "RUN_NOT_WAITING",
            "This run is not currently waiting for an approval callback.",
            run_id,
        )

    new_status = RunStatus.RUNNING if decision == "approve" else RunStatus.CANCELADO

    try:
        runs_table.approve_or_reject(
            run_id, sub=sub, plan_hash=plan_hash, new_status=new_status.value
        )
    except ApprovalConflictError:
        return _error_response(
            409,
            "APPROVAL_CONFLICT",
            "This run is no longer AWAITING_APPROVAL with that plan_hash "
            "(it may have already been decided, or the plan changed).",
            run_id,
        )

    if run.awaiting_approval_since is not None:
        waited = (datetime.now(UTC) - run.awaiting_approval_since).total_seconds()
        run.approval_wait_seconds += waited
        run.status = new_status
        runs_table.put(run)
        log_event("api.approval_recorded", run_id=run_id, decision=decision, waited_seconds=round(waited, 1))

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
            return _error_response(
                409,
                "RUN_NO_LONGER_WAITING",
                "This run stopped waiting for approval before the decision reached it.",
                run_id,
            )

        run.status = RunStatus.AWAITING_APPROVAL
        runs_table.put(run)
        return _error_response(
            503,
            "APPROVAL_CALLBACK_FAILED",
            "The decision was recorded but could not be delivered. Retry shortly.",
            run_id,
        )

    run.status = new_status
    return _ok_response(200, run.model_dump(mode="json", exclude={"task_token"}))


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    runs_table = RunsTable()
    sfn_client = boto3.client("stepfunctions")

    method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod")
    path_params = event.get("pathParameters") or {}
    raw_path = event.get("rawPath") or event.get("path") or ""

    log_event(
        "api.request",
        method=method,
        path=raw_path,
        query=event.get("queryStringParameters") or {},
        path_params=path_params,
        requested_by=_requested_by(event),
        body=_loggable_body(event),
    )

    try:
        if method == "POST" and "run_id" not in path_params:
            response = create_run(event, runs_table, sfn_client)
        elif method == "POST" and path_params.get("run_id") and raw_path.endswith("/approval"):
            response = handle_approval(event, runs_table, sfn_client)
        elif method == "GET" and path_params.get("run_id") and raw_path.endswith("/report"):
            response = get_report(event, runs_table, boto3.resource("s3"), EventsTable())
        elif method == "GET" and path_params.get("run_id"):
            response = get_run(event, runs_table)
        elif method == "GET" and "run_id" not in path_params:
            response = list_runs(event, runs_table)
        else:
            response = _error_response(404, "ROUTE_NOT_FOUND", "No route matches this request.", None)
    except Exception as exc:
        log_event(
            "api.unhandled_error",
            method=method,
            path=raw_path,
            error_type=type(exc).__name__,
            error=str(exc)[:500],
        )
        raise

    status = response.get("statusCode")
    log_event(
        "api.response",
        method=method,
        path=raw_path,
        status=status,
        body=response.get("body", "")[:2000] if status and status >= 400 else None,
    )
    return response
