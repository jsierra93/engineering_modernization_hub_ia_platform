"""lambda api handler: creates, lists, reads and approves runs, and serves the report.
Does not call Bedrock directly; objective resolution lives in api/resolver.
"""

from __future__ import annotations

import functools
import json
import os
import time
import uuid
from datetime import UTC, datetime
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
SANDBOX_TASK_DEFINITIONS_ENV = "MODHUB_SANDBOX_TASK_DEFINITIONS"
APPROVAL_MAX_AUTH_AGE_SECONDS_ENV = "MODHUB_APPROVAL_MAX_AUTH_AGE_SECONDS"
DEV_STRATEGY_ID_ENV = "MODHUB_DEV_STRATEGY_ID"
REPO_ALLOWLIST_ENV = "MODHUB_REPO_ALLOWLIST"
DEFAULT_APPROVAL_MAX_AUTH_AGE_SECONDS = 300
REQUIRED_RUN_FIELDS = ("repo", "commit", "objetivo", "max_usd", "max_iterations", "max_minutes")
SECURITY_EVENT_TYPES = ("SecurityBlocked",)


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


class _Reject(Exception):
    def __init__(self, status_code: int, code: str, message: str, run_id: str | None = None) -> None:
        super().__init__(message)
        self.response = _error_response(status_code, code, message, run_id)


def _returns_rejections(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except _Reject as rejection:
            return rejection.response

    return wrapper


def _claims(event: dict[str, Any]) -> dict[str, Any]:
    return event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})


def _requested_by(event: dict[str, Any]) -> str:
    if _claims(event).get("sub"):
        return _claims(event)["sub"]
    headers = event.get("headers") or {}
    return headers.get("x-requested-by") or headers.get("X-Requested-By") or "anonymous"


def _get_trace_id(event: dict[str, Any]) -> str:
    headers = event.get("headers") or {}
    return headers.get("x-trace-id") or headers.get("X-Trace-Id") or str(uuid.uuid4())


def _auth_is_recent(event: dict[str, Any]) -> bool:
    auth_time = _claims(event).get("auth_time")
    if auth_time is None:
        return True
    max_age_seconds = int(
        os.environ.get(APPROVAL_MAX_AUTH_AGE_SECONDS_ENV, DEFAULT_APPROVAL_MAX_AUTH_AGE_SECONDS)
    )
    return (time.time() - int(auth_time)) <= max_age_seconds


def _loggable_body(event: dict[str, Any]) -> Any:
    raw = event.get("body") or ""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw[:2000]


def _parse_json_body(event: dict[str, Any], run_id: str | None = None) -> Any:
    try:
        return json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        raise _Reject(400, "INVALID_BODY", "Request body is not valid JSON.", run_id) from None


def _path_run_id(event: dict[str, Any], *, require_uuid: bool) -> str:
    run_id = (event.get("pathParameters") or {}).get("run_id")
    if not run_id:
        raise _Reject(400, "MISSING_RUN_ID", "run_id path parameter is required.")
    if require_uuid:
        try:
            uuid.UUID(run_id)
        except ValueError:
            raise _Reject(400, "INVALID_RUN_ID", "run_id must be a UUID.", run_id) from None
    return run_id


def _load_own_run(event: dict[str, Any], runs_table: RunsTable, run_id: str) -> Run:
    run = runs_table.get(run_id)
    # Someone else's run answers 404, not 403, so a guessed run_id confirms nothing.
    if run is None or run.requested_by != _requested_by(event):
        raise _Reject(404, "RUN_NOT_FOUND", "No run with that id.", run_id)
    return run


def _public_run(run: Run) -> dict[str, Any]:
    return run.model_dump(mode="json", exclude={"task_token"})


def _parse_create_body(event: dict[str, Any]) -> Any:
    body = _parse_json_body(event)
    missing = [field for field in REQUIRED_RUN_FIELDS if field not in body]
    if missing:
        raise _Reject(422, "MISSING_FIELDS", f"Missing required fields: {', '.join(missing)}")
    return body


def _check_repo_allowed(body: dict[str, Any]) -> None:
    allowlist = [entry.strip() for entry in os.environ.get(REPO_ALLOWLIST_ENV, "").split(",") if entry.strip()]
    repo = str(body.get("repo", ""))
    if allowlist and repo not in allowlist and f"{repo.split('/', 1)[0]}/*" not in allowlist:
        raise _Reject(
            403,
            "REPO_NOT_ALLOWED",
            f"{body.get('repo')!r} is not on this deployment's repository allowlist.",
        )


def _resolve_manifest(body: dict[str, Any], trace_id: str, bedrock_client: Any):
    candidates = list_strategy_manifests()
    dev_strategy_id = os.environ.get(DEV_STRATEGY_ID_ENV)
    if dev_strategy_id:
        manifest = next((m for m in candidates if m.id == dev_strategy_id), None)
        if manifest is None:
            raise _Reject(
                500,
                "DEV_STRATEGY_MISCONFIGURED",
                f"{DEV_STRATEGY_ID_ENV}={dev_strategy_id!r} does not match any registered strategy.",
            )
        return manifest, 1.0
    try:
        return resolve_strategy(body["objetivo"], candidates, bedrock_client=bedrock_client)
    except NoStrategyMatchError as exc:
        raise _Reject(422, "NO_STRATEGY_MATCH", str(exc)) from None
    except ResolverUnavailableError as exc:
        log_event("api.resolver_unavailable", trace_id=trace_id, error=str(exc)[:300])
        raise _Reject(
            503, "RESOLVER_UNAVAILABLE", "The objective could not be resolved right now. Retry shortly."
        ) from None


def _validate_limits(body: dict[str, Any], manifest: Any, trace_id: str) -> None:
    for field in LIMIT_FIELDS:
        value = body[field]
        # bool is an int subclass, so it must be rejected explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _Reject(422, "INVALID_LIMIT", f"{field} must be a number, got {type(value).__name__}.")
        if value <= 0:
            raise _Reject(422, "INVALID_LIMIT", f"{field} must be greater than zero.")
    try:
        resolve_limits({field: body[field] for field in LIMIT_FIELDS}, manifest.limits, platform_ceiling().as_dict())
    except LimitsRequestError as exc:
        raise _Reject(
            422,
            "LIMIT_EXCEEDS_STRATEGY_MAX",
            f"requested {exc.field}={exc.requested} exceeds strategy {manifest.id}'s max of {exc.maximum}.",
        ) from None
    except LimitsConfigurationError as exc:
        log_event("api.strategy_limits_misconfigured", strategy_id=manifest.id, error=str(exc)[:300], trace_id=trace_id)
        raise _Reject(
            500, "STRATEGY_MISCONFIGURED", "The resolved strategy declares limits above the platform ceiling."
        ) from None


def _build_run(body: dict[str, Any], manifest: Any, requested_by: str, trace_id: str) -> Run:
    try:
        return Run(
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
        problems = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors())
        log_event("api.invalid_request", trace_id=trace_id, problems=problems)
        raise _Reject(422, "INVALID_REQUEST", problems) from None


def _sandbox_task_definition(manifest: Any) -> str:
    arns = json.loads(os.environ.get(SANDBOX_TASK_DEFINITIONS_ENV, "{}"))
    arn = arns.get(manifest.sandbox_profile)
    if arn is None:
        raise _Reject(503, "SANDBOX_PROFILE_UNAVAILABLE", f"no sandbox is deployed for profile {manifest.sandbox_profile!r}")
    return arn


def _start_execution(sfn_client: Any, run: Run, trace_id: str, sandbox_task_definition_arn: str) -> None:
    state_machine_arn = os.environ[STATE_MACHINE_ARN_ENV]
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
                "sandbox_task_definition_arn": sandbox_task_definition_arn,
                "max_iterations": run.max_iterations,
                "excluded_paths": run.restricciones.excluded_paths,
                "iteration": 0,
            }
        ),
    )


@_returns_rejections
def create_run(
    event: dict[str, Any],
    runs_table: RunsTable,
    sfn_client: Any,
    bedrock_client: Any = None,
) -> dict[str, Any]:
    trace_id = _get_trace_id(event)
    body = _parse_create_body(event)
    _check_repo_allowed(body)
    manifest, match_confidence = _resolve_manifest(body, trace_id, bedrock_client)
    _validate_limits(body, manifest, trace_id)
    sandbox_task_definition_arn = _sandbox_task_definition(manifest)
    requested_by = _requested_by(event)
    run = _build_run(body, manifest, requested_by, trace_id)

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
    _start_execution(sfn_client, run, trace_id, sandbox_task_definition_arn)

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


def list_runs(event: dict[str, Any], runs_table: RunsTable) -> dict[str, Any]:
    status = (event.get("queryStringParameters") or {}).get("status")
    runs = runs_table.query_by_requested_by(_requested_by(event))
    if status:
        runs = [run for run in runs if run.status.value == status]
    runs.sort(key=lambda run: run.created_at, reverse=True)
    return _ok_response(200, {"items": [_public_run(run) for run in runs]})


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


@_returns_rejections
def get_report(
    event: dict[str, Any],
    runs_table: RunsTable,
    s3_resource: Any = None,
    events_table: EventsTable | None = None,
) -> dict[str, Any]:
    run_id = _path_run_id(event, require_uuid=False)
    run = _load_own_run(event, runs_table, run_id)

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


@_returns_rejections
def get_run(event: dict[str, Any], runs_table: RunsTable) -> dict[str, Any]:
    run_id = _path_run_id(event, require_uuid=True)
    return _ok_response(200, _public_run(_load_own_run(event, runs_table, run_id)))


def _parse_decision(body: dict[str, Any], run_id: str) -> tuple[str, str]:
    decision = body.get("decision")
    plan_hash = body.get("plan_hash")
    if decision not in ("approve", "reject") or not plan_hash:
        raise _Reject(422, "MISSING_FIELDS", "decision (approve|reject) and plan_hash are required.", run_id)
    return decision, plan_hash


def _authorize_approval(event: dict[str, Any], run: Run, run_id: str) -> str:
    sub = _requested_by(event)
    if sub != run.requested_by:
        raise _Reject(403, "NOT_REQUESTER", "Only the user who requested this run may approve or reject it.", run_id)
    if not _auth_is_recent(event):
        raise _Reject(401, "AUTH_NOT_RECENT", "Re-authenticate before approving or rejecting a run.", run_id)
    # Checked before the conditional write: without a token the callback cannot resume the execution.
    if not run.task_token:
        log_event("api.approval_without_token", run_id=run_id, status=run.status.value)
        raise _Reject(409, "RUN_NOT_WAITING", "This run is not currently waiting for an approval callback.", run_id)
    return sub


def _record_decision(
    runs_table: RunsTable, run: Run, run_id: str, sub: str, plan_hash: str, decision: str, new_status: RunStatus
) -> None:
    try:
        runs_table.approve_or_reject(run_id, sub=sub, plan_hash=plan_hash, new_status=new_status.value)
    except ApprovalConflictError:
        raise _Reject(
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
            raise _Reject(
                409,
                "RUN_NO_LONGER_WAITING",
                "This run stopped waiting for approval before the decision reached it.",
                run_id,
            ) from None
        run.status = RunStatus.AWAITING_APPROVAL
        runs_table.update_fields(run, "status")
        raise _Reject(
            503,
            "APPROVAL_CALLBACK_FAILED",
            "The decision was recorded but could not be delivered. Retry shortly.",
            run_id,
        ) from None


@_returns_rejections
def handle_approval(event: dict[str, Any], runs_table: RunsTable, sfn_client: Any) -> dict[str, Any]:
    run_id = _path_run_id(event, require_uuid=True)
    body = _parse_json_body(event, run_id)
    decision, plan_hash = _parse_decision(body, run_id)

    run = runs_table.get(run_id)
    if run is None:
        raise _Reject(404, "RUN_NOT_FOUND", "No run with that id.", run_id)
    sub = _authorize_approval(event, run, run_id)

    new_status = RunStatus.RUNNING if decision == "approve" else RunStatus.CANCELADO
    _record_decision(runs_table, run, run_id, sub, plan_hash, decision, new_status)
    _deliver_decision(sfn_client, runs_table, run, run_id, decision, plan_hash, body)

    run.status = new_status
    return _ok_response(200, _public_run(run))


def _match_route(method: str | None, path_params: dict[str, Any], raw_path: str) -> str | None:
    has_key = "run_id" in path_params
    has_id = bool(path_params.get("run_id"))
    if method == "POST" and not has_key:
        return "create_run"
    if method == "POST" and has_id and raw_path.endswith("/approval"):
        return "approval"
    if method == "GET" and has_id and raw_path.endswith("/report"):
        return "report"
    if method == "GET" and has_id:
        return "get_run"
    if method == "GET" and not has_key:
        return "list_runs"
    return None


_ROUTES = {
    "create_run": lambda event, runs: create_run(event, runs, boto3.client("stepfunctions")),
    "approval": lambda event, runs: handle_approval(event, runs, boto3.client("stepfunctions")),
    "report": lambda event, runs: get_report(event, runs, boto3.resource("s3"), EventsTable()),
    "get_run": get_run,
    "list_runs": list_runs,
}


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    runs_table = RunsTable()

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
        route = _match_route(method, path_params, raw_path)
        if route is None:
            response = _error_response(404, "ROUTE_NOT_FOUND", "No route matches this request.", None)
        else:
            response = _ROUTES[route](event, runs_table)
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
