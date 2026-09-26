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
import uuid
from typing import Any

import boto3

from core_py.models import Restricciones, Run, RunStatus
from core_py.persistence import RunsTable

# Stubbed until the Fase 4 resolver (services/api/resolver/) lands.
STUB_STRATEGY_ID = "python-pydantic-v2"
STUB_STRATEGY_VERSION = "1.0.0"
STUB_MATCH_CONFIDENCE = 1.0

STATE_MACHINE_ARN_ENV = "MODHUB_STATE_MACHINE_ARN"


class NoStrategyMatchError(Exception):
    """Raised when the free-text objetivo cannot be resolved to a strategy.

    Not used by the stubbed resolver in this pass (it always matches),
    but kept so the 422 NO_STRATEGY_MATCH contract path is exercised once
    Fase 4 wires the real resolver in.
    """


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
    """Extract the caller's sub. No Cognito authorizer is wired yet
    (that's Fase 4, task 4.2-tf) so this falls back to a header for local
    testing."""
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


def create_run(
    event: dict[str, Any],
    runs_table: RunsTable,
    sfn_client: Any,
) -> dict[str, Any]:
    """Handle `POST /modhub/v1/runs`."""

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

    run = Run(
        repo=body["repo"],
        commit=body["commit"],
        objetivo=body["objetivo"],
        inputs=body.get("inputs", {}),
        restricciones=Restricciones(**body.get("restricciones", {})),
        requested_by=requested_by,
        strategy_id=STUB_STRATEGY_ID,
        strategy_version=STUB_STRATEGY_VERSION,
        max_usd=body["max_usd"],
        max_iterations=body["max_iterations"],
        max_minutes=body["max_minutes"],
        status=RunStatus.PENDING,
    )

    runs_table.put(run)

    state_machine_arn = os.environ.get(STATE_MACHINE_ARN_ENV, "arn:aws:states:local:000000000000:stateMachine:modhub-stub")
    sfn_client.start_execution(
        stateMachineArn=state_machine_arn,
        name=str(run.run_id),
        input=json.dumps({"run_id": str(run.run_id)}),
    )

    return _ok_response(
        201,
        {
            "run_id": str(run.run_id),
            "status": run.status.value,
            "resolved_strategy": {
                "id": run.strategy_id,
                "version": run.strategy_version,
                "match_confidence": STUB_MATCH_CONFIDENCE,
            },
            "requested_by": run.requested_by,
            "created_at": run.created_at.isoformat(),
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

    run = runs_table.get(run_id)
    if run is None:
        return _error_response(404, "RUN_NOT_FOUND", "No run with that id.", run_id)

    return _ok_response(200, run.model_dump(mode="json"))


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

    if method == "POST" and "run_id" not in path_params:
        return create_run(event, runs_table, sfn_client)
    if method == "GET" and path_params.get("run_id"):
        return get_run(event, runs_table)

    return _error_response(404, "ROUTE_NOT_FOUND", "No route matches this request.", None)
