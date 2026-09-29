"""HTTP plumbing shared by every route: response shapes, the rejection type, body and path parsing."""

from __future__ import annotations

import functools
import json
import uuid
from typing import Any

from core_py.models import Run


def error_response(status_code: int, code: str, message: str, run_id: str | None) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"code": code, "message": message, "run_id": run_id}),
    }


def ok_response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    }


class Reject(Exception):
    def __init__(self, status_code: int, code: str, message: str, run_id: str | None = None) -> None:
        super().__init__(message)
        self.response = error_response(status_code, code, message, run_id)


def returns_rejections(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Reject as rejection:
            return rejection.response

    return wrapper


def get_trace_id(event: dict[str, Any]) -> str:
    headers = event.get("headers") or {}
    return headers.get("x-trace-id") or headers.get("X-Trace-Id") or str(uuid.uuid4())


def loggable_body(event: dict[str, Any]) -> Any:
    raw = event.get("body") or ""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw[:2000]


def parse_json_body(event: dict[str, Any], run_id: str | None = None) -> Any:
    try:
        return json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        raise Reject(400, "INVALID_BODY", "Request body is not valid JSON.", run_id) from None


def path_run_id(event: dict[str, Any], *, require_uuid: bool) -> str:
    run_id = (event.get("pathParameters") or {}).get("run_id")
    if not run_id:
        raise Reject(400, "MISSING_RUN_ID", "run_id path parameter is required.")
    if require_uuid:
        try:
            uuid.UUID(run_id)
        except ValueError:
            raise Reject(400, "INVALID_RUN_ID", "run_id must be a UUID.", run_id) from None
    return run_id


def public_run(run: Run) -> dict[str, Any]:
    return run.model_dump(mode="json", exclude={"task_token"})
