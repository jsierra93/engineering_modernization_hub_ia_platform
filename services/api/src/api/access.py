"""Who may see or decide on a run: ownership of a run and how recent the caller's login must be."""

from __future__ import annotations

import os
from typing import Any

from core_py.identity import auth_is_recent, caller_sub, is_owner
from core_py.models import Run
from core_py.persistence import RunsTable

from api.responses import Reject


APPROVAL_MAX_AUTH_AGE_SECONDS_ENV = "MODHUB_APPROVAL_MAX_AUTH_AGE_SECONDS"
DEFAULT_APPROVAL_MAX_AUTH_AGE_SECONDS = 300


def caller_auth_is_recent(event: dict[str, Any]) -> bool:
    max_age_seconds = int(os.environ.get(APPROVAL_MAX_AUTH_AGE_SECONDS_ENV, DEFAULT_APPROVAL_MAX_AUTH_AGE_SECONDS))
    return auth_is_recent(event, max_age_seconds)


def require_caller(event: dict[str, Any]) -> str:
    sub = caller_sub(event)
    if sub is None:
        raise Reject(401, "UNAUTHENTICATED", "A signed-in caller is required.")
    return sub


def load_own_run(event: dict[str, Any], runs_table: RunsTable, run_id: str) -> Run:
    require_caller(event)
    run = runs_table.get(run_id)
    # Someone else's run answers 404, not 403, so a guessed run_id confirms nothing.
    if run is None or not is_owner(event, run.requested_by):
        raise Reject(404, "RUN_NOT_FOUND", "No run with that id.", run_id)
    return run
