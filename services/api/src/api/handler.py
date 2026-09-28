"""Minimal Lambda handler for `POST /modhub/v1/runs` and
`GET /modhub/v1/runs/{run_id}`.

Scope for this scaffolding pass (PLAN.md Fase 1, task 1.6):

- `strategy_id` is hardcoded/stubbed here. The real Bedrock-based
  objective -> strategy resolver is Fase 4 (task 4.4) and lives in
  `services/api/resolver/`, isolated per CLAUDE.md's one documented
  Bedrock exception. This handler must not call Bedrock.
- Starting the Step Functions execution uses a boto3 client so it can be
  mocked in tests; the real state machine is Fase 1's task 1.5-tf.
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

from core_py.models import Restricciones, Run, RunStatus
from core_py.observability import log_event
from core_py.persistence import ApprovalConflictError, EventsTable, RunsTable

from api.resolver import NoStrategyMatchError, ResolverUnavailableError, resolve_strategy
from api.strategy_lookup import list_strategy_manifests

STATE_MACHINE_ARN_ENV = "MODHUB_STATE_MACHINE_ARN"
WORKSPACE_BUCKET_ENV = "MODHUB_WORKSPACE_BUCKET"

APPROVAL_MAX_AUTH_AGE_SECONDS_ENV = "MODHUB_APPROVAL_MAX_AUTH_AGE_SECONDS"

DEV_STRATEGY_ID_ENV = "MODHUB_DEV_STRATEGY_ID"

# Comma-separated `owner/name` or `owner/*`. Unset means any well-formed
# repo, which is the prototype's posture: the requester supplies the
# repository and the sandbox has no credentials to abuse. The hook exists
# because the design document already promised this control, and because
# an internal deployment would want it.
REPO_ALLOWLIST_ENV = "MODHUB_REPO_ALLOWLIST"
DEFAULT_APPROVAL_MAX_AUTH_AGE_SECONDS = 300

# CLAUDE.md invariant #5: request <= strategy max <= platform ceiling.
# Registration (strategies_sdk.registry.StrategyRegistry.register) already
# enforces strategy-max <= platform-ceiling; this is the remaining link --
# a request may only tighten the resolved strategy's own max, never exceed
# it. Duplicated as a plain loop here rather than importing
# core_ops.limits.resolve_limits: api and core_ops are separately packaged
# Lambdas (see api/strategy_lookup.py's own comment on this boundary).
LIMIT_FIELDS = ("max_usd", "max_iterations", "max_minutes")


def _repo_is_allowed(repo: str, allowlist: list[str]) -> bool:
    owner = repo.split("/", 1)[0]
    return repo in allowlist or f"{owner}/*" in allowlist


def _loggable_body(event: dict[str, Any]) -> Any:
    """The request body, never the headers: those carry the bearer token."""

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
    """The caller's `sub`, which every Cognito token carries -- it is a
    required OIDC claim, and for a machine-to-machine token it is the app
    client id rather than being absent.

    The header fallback only ever runs where no JWT authorizer did (the
    local env, which sets `enable_jwt_authorizer = false`). With the
    authorizer on, API Gateway rejects the request before this code runs,
    so the header cannot be used to impersonate anyone. It resolves to a
    sub that owns no runs, so every scoping decision built on it fails
    closed."""
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
    """The run, if it belongs to the caller. Otherwise the 404 to return.

    A run someone else requested is reported as not found, not as
    forbidden: 403 would confirm that a given run_id exists, which is the
    one thing an unauthorized caller could learn from an id they guessed.
    Approval answers 403 instead, deliberately -- there the caller already
    holds the id from their own inbox, and "you may not approve this" is
    more useful than pretending it is missing.
    """

    run = runs_table.get(run_id)
    if run is None or run.requested_by != _requested_by(event):
        return None, _error_response(404, "RUN_NOT_FOUND", "No run with that id.", run_id)
    return run, None


def _get_trace_id(event: dict[str, Any]) -> str:
    """Extract or generate trace_id for distributed tracing.
    Follows W3C Trace Context convention (x-trace-id header).
    If x-trace-id header exists, use it; otherwise generate new UUID."""
    headers = event.get("headers") or {}
    return headers.get("x-trace-id") or headers.get("X-Trace-Id") or str(uuid.uuid4())


def _auth_is_recent(event: dict[str, Any]) -> bool:
    """CLAUDE.md invariant #7: approval requires 'auth is recent', not
    just a validly-signed-but-old token. A real Cognito JWT always carries
    `auth_time` (when the user actually authenticated, not when this
    particular access token was minted/refreshed). No `auth_time` means
    no real JWT authorizer ran (local/dev's x-requested-by fallback, Fase
    4 task 4.2-tf not enabled) -- nothing to check in that path."""

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
    """Handle `POST /modhub/v1/runs`."""

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
        # Local-dev-only escape hatch (2026-09-26), same shape as
        # modhub-backend's devToken: Floci doesn't emulate real Bedrock
        # inference, so resolve_strategy's own call always comes back
        # unusable here regardless of `objetivo` -- confirmed empirically,
        # not a hypothetical. When set, skip Bedrock entirely and use this
        # strategy id directly, so the rest of the flow (FetchRepo,
        # Baseline, ...) is still exercisable against Floci. Unset in
        # envs/personal -- see infrastructure/envs/local/main.tf's own
        # comment on where this env var is set, and DELETE it there too
        # once testing against real AWS Bedrock specifically.
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
            # No client built here on purpose: the one documented Bedrock
            # call stays inside services/api/resolver (CLAUDE.md).
            manifest, match_confidence = resolve_strategy(
                body["objetivo"], candidates, bedrock_client=bedrock_client
            )
        except NoStrategyMatchError as exc:
            return _error_response(422, "NO_STRATEGY_MATCH", str(exc), None)
        except ResolverUnavailableError as exc:
            # Retryable and not the caller's fault -- a throttle answered
            # 500 before, which reads as "this request is broken" rather
            # than "try again". No run exists yet, so there is nothing to
            # mark FALLIDO_CONTROLADO.
            log_event("api.resolver_unavailable", trace_id=trace_id, error=str(exc)[:300])
            return _error_response(
                503,
                "RESOLVER_UNAVAILABLE",
                "The objective could not be resolved right now. Retry shortly.",
                None,
            )

    for field in LIMIT_FIELDS:
        value = body[field]
        # `bool` is a subclass of `int`, so `max_usd: true` would sail past
        # a plain isinstance check and compare as 1 -- accepted in silence
        # with a nonsensical limit. And comparing a str against a float
        # raises TypeError here, turning bad input into a 500 before the
        # model ever sees it.
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

        limit_max = getattr(manifest.limits, field).max
        if value > limit_max:
            return _error_response(
                422,
                "LIMIT_EXCEEDS_STRATEGY_MAX",
                f"requested {field}={value} exceeds strategy {manifest.id}'s max of {limit_max}.",
                None,
            )

    # Every constraint below -- the 40-character commit, a non-empty
    # objetivo, `extra="forbid"` on restricciones -- is a statement about
    # the request, so breaking one is the caller's error, not the server's.
    # Uncaught, pydantic's ValidationError propagated and API Gateway
    # answered 500, which tells a client "retry, the server is broken" for
    # input that will fail identically every time.
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
        # Everything downstream states need and can't derive from a prior
        # phase's own result rides along in this initial input -- Step
        # Functions' ResultPath merges preserve these across every later
        # state (see orchestration's ASL), so they never need re-threading.
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
    """Handle `GET /modhub/v1/runs?mine=&status=`.

    A real gap closed during Fase 5's Backstage work: the artifact's own
    API table and packages/contracts/openapi.yaml both document this
    route (it backs `modhub inbox`/`modhub runs` and Backstage's
    Modernizaciones list), but no handler existed for it before now.

    Always scoped to the caller's own `sub`. `mine` is accepted and
    ignored: a caller can only act on their own runs (invariant #7 gates
    approval on `sub == requested_by`), so listing anyone else's was
    surfacing rows nothing could be done with. Scoping in the client was
    a filter; scoping here is a control.

    Fails closed by construction: with no JWT claims `_requested_by`
    yields a sub that owns no runs, which returns an empty list -- never
    the whole table.
    """

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
    """The run's security events, for the report.

    The brief's injection scenario requires the platform to "registrar el
    evento". They are written to the events table by core_ops, but until
    now nothing surfaced them: the control worked and left no visible
    trace, which is not evidence. Read-only here -- lambda api has Query
    and no write permission on that table, so the report cannot alter the
    audit trail it displays."""

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
    """Fetch the diff from S3 so the report stays self-contained.

    Read on demand rather than stored on the run: a diff can reach
    hundreds of KB and a DynamoDB item tops out at 400 KB. A missing or
    unreadable object degrades to no diff -- it is evidence attached to a
    verdict, never an input to it, so it must not fail the report."""

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
    """Handle `GET /modhub/v1/runs/{run_id}/report` -- what the run
    delivers: the verdict core_ops computed, the diff it measured from S3,
    and the agent's own narrative. Separate authors, one document
    (CLAUDE.md invariant #10)."""

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
    """Handle `GET /modhub/v1/runs/{run_id}`."""

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

    # task_token is an internal Step Functions callback detail (Fase 4),
    # never part of the public API contract -- see packages/contracts/
    # openapi.yaml's Run schema and its own test for why.
    return _ok_response(200, run.model_dump(mode="json", exclude={"task_token"}))


def handle_approval(
    event: dict[str, Any],
    runs_table: RunsTable,
    sfn_client: Any,
) -> dict[str, Any]:
    """Handle `POST /modhub/v1/runs/{run_id}/approval`.

    "Quien crea la solicitud es quien la aprueba" (CLAUDE.md): the 403
    identity check happens here, against the run as it exists right now,
    *before* the atomic conditional update -- so a caller who is simply
    the wrong person gets 403, and only a genuine race (state changed,
    plan changed, or a resubmit) reaches the 409 the DB condition raises.
    """

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

    # Before the conditional write, not after. The callback is the only
    # thing that actually resumes the execution; without a token there is
    # nothing to call, and writing the status first would leave the run
    # reading RUNNING while the state machine sat in AwaitApproval until
    # its timeout -- which would then report APPROVAL_TIMED_OUT and blame
    # a human who did approve. Failing here keeps the run in
    # AWAITING_APPROVAL, where the timeout still means what it says.
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

    # The Run row we already read still carries the task_token recorded by
    # AwaitApproval (record_task_token) -- reading it again post-update
    # would just refetch the same value now paired with the new status.
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
            # The execution already stopped waiting -- AwaitApproval hit
            # its timeout, or the run ended some other way. Nothing to
            # resume and nothing to retry, so the status stays where the
            # conditional write left it rather than pretending the run is
            # back in the queue.
            return _error_response(
                409,
                "RUN_NO_LONGER_WAITING",
                "This run stopped waiting for approval before the decision reached it.",
                run_id,
            )

        # Anything else is transient. Put the run back where it was so the
        # same request can simply be retried -- leaving it decided would
        # make every retry fail the conditional write with a 409 and strand
        # the requester with no way forward.
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
    """Lambda entrypoint, dispatching on HTTP method + route.

    Real deployments inject the DynamoDB/Step Functions clients via the
    default boto3 constructors; tests pass moto-backed / mocked clients
    through `create_run`/`get_run` directly.
    """

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
        # Re-raised so the state machine / API Gateway still see the failure;
        # logged first because an unhandled traceback alone does not say which
        # request produced it.
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
