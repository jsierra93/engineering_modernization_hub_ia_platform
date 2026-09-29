"""Lambda entrypoint for /modhub/v1: matches the route and delegates. No business rules live here."""

from __future__ import annotations

from typing import Any

import boto3

from core_py.identity import caller_sub
from core_py.observability import log_event
from core_py.persistence import EventsTable, RunsTable

from api.approvals import handle_approval
from api.create import create_run
from api.read import get_report, get_run, list_runs
from api.responses import error_response, loggable_body


_ROUTES = {
    "create_run": lambda event, runs: create_run(event, runs, boto3.client("stepfunctions")),
    "approval": lambda event, runs: handle_approval(event, runs, boto3.client("stepfunctions")),
    "report": lambda event, runs: get_report(event, runs, boto3.resource("s3"), EventsTable()),
    "get_run": get_run,
    "list_runs": list_runs,
}


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
        requested_by=caller_sub(event),
        body=loggable_body(event),
    )

    try:
        route = _match_route(method, path_params, raw_path)
        if route is None:
            response = error_response(404, "ROUTE_NOT_FOUND", "No route matches this request.", None)
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
