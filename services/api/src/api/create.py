"""POST /runs: validates the request, resolves the strategy, creates the run and starts its execution."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import ValidationError

from api.resolver import NoStrategyMatchError, ResolverUnavailableError, resolve_strategy
from core_py.limits import LIMIT_FIELDS, LimitsConfigurationError, LimitsRequestError, platform_ceiling, resolve_limits
from core_py.models import Restricciones, Run, RunStatus
from core_py.observability import log_event
from core_py.persistence import RunsTable
from core_py.strategy_catalog import list_strategy_manifests

from api.access import require_caller
from api.responses import Reject, get_trace_id, ok_response, parse_json_body, returns_rejections


STATE_MACHINE_ARN_ENV = "MODHUB_STATE_MACHINE_ARN"
SANDBOX_TASK_DEFINITIONS_ENV = "MODHUB_SANDBOX_TASK_DEFINITIONS"
DEV_STRATEGY_ID_ENV = "MODHUB_DEV_STRATEGY_ID"
REPO_ALLOWLIST_ENV = "MODHUB_REPO_ALLOWLIST"
REQUIRED_RUN_FIELDS = ("repo", "commit", "objetivo", "max_usd", "max_iterations", "max_minutes")


def _parse_create_body(event: dict[str, Any]) -> Any:
    body = parse_json_body(event)
    missing = [field for field in REQUIRED_RUN_FIELDS if field not in body]
    if missing:
        raise Reject(422, "MISSING_FIELDS", f"Missing required fields: {', '.join(missing)}")
    return body


def _check_repo_allowed(body: dict[str, Any]) -> None:
    allowlist = [entry.strip() for entry in os.environ.get(REPO_ALLOWLIST_ENV, "").split(",") if entry.strip()]
    repo = str(body.get("repo", ""))
    if allowlist and repo not in allowlist and f"{repo.split('/', 1)[0]}/*" not in allowlist:
        raise Reject(
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
            raise Reject(
                500,
                "DEV_STRATEGY_MISCONFIGURED",
                f"{DEV_STRATEGY_ID_ENV}={dev_strategy_id!r} does not match any registered strategy.",
            )
        return manifest, 1.0
    try:
        return resolve_strategy(body["objetivo"], candidates, bedrock_client=bedrock_client)
    except NoStrategyMatchError as exc:
        raise Reject(422, "NO_STRATEGY_MATCH", str(exc)) from None
    except ResolverUnavailableError as exc:
        log_event("api.resolver_unavailable", trace_id=trace_id, error=str(exc)[:300])
        raise Reject(
            503, "RESOLVER_UNAVAILABLE", "The objective could not be resolved right now. Retry shortly."
        ) from None


def _validate_limits(body: dict[str, Any], manifest: Any, trace_id: str) -> None:
    for field in LIMIT_FIELDS:
        value = body[field]
        # bool is an int subclass, so it must be rejected explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Reject(422, "INVALID_LIMIT", f"{field} must be a number, got {type(value).__name__}.")
        if value <= 0:
            raise Reject(422, "INVALID_LIMIT", f"{field} must be greater than zero.")
    try:
        resolve_limits({field: body[field] for field in LIMIT_FIELDS}, manifest.limits, platform_ceiling().as_dict())
    except LimitsRequestError as exc:
        raise Reject(
            422,
            "LIMIT_EXCEEDS_STRATEGY_MAX",
            f"requested {exc.field}={exc.requested} exceeds strategy {manifest.id}'s max of {exc.maximum}.",
        ) from None
    except LimitsConfigurationError as exc:
        log_event("api.strategy_limits_misconfigured", strategy_id=manifest.id, error=str(exc)[:300], trace_id=trace_id)
        raise Reject(
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
        raise Reject(422, "INVALID_REQUEST", problems) from None


def _sandbox_task_definition(manifest: Any) -> str:
    arns = json.loads(os.environ.get(SANDBOX_TASK_DEFINITIONS_ENV, "{}"))
    arn = arns.get(manifest.sandbox_profile)
    if arn is None:
        raise Reject(503, "SANDBOX_PROFILE_UNAVAILABLE", f"no sandbox is deployed for profile {manifest.sandbox_profile!r}")
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
                "max_usd": run.max_usd,
                "max_iterations": run.max_iterations,
                "excluded_paths": run.restricciones.excluded_paths,
                "iteration": 0,
            }
        ),
    )


@returns_rejections
def create_run(
    event: dict[str, Any],
    runs_table: RunsTable,
    sfn_client: Any,
    bedrock_client: Any = None,
) -> dict[str, Any]:
    requested_by = require_caller(event)
    trace_id = get_trace_id(event)
    body = _parse_create_body(event)
    _check_repo_allowed(body)
    manifest, match_confidence = _resolve_manifest(body, trace_id, bedrock_client)
    _validate_limits(body, manifest, trace_id)
    sandbox_task_definition_arn = _sandbox_task_definition(manifest)
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

    return ok_response(
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
