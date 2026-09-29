"""Workspace steps the state machine runs between the agent and the sandbox: the working copy and the sandbox handoff.
They are deterministic and live here, not in the agent's Lambda, so the LLM zone never copies, packages or signs anything.
"""

from __future__ import annotations

from typing import Any

from core_py.constants import BASELINE_VERSION, WORKING_VERSION
from core_py.observability import log_event
from core_py.workspace import copy_version, prepare_sandbox_io


def snapshot_workspace(event: dict[str, Any], s3_resource: Any) -> dict[str, Any]:
    run_id = event["run_id"]
    copied = copy_version(s3_resource, event["workspaces_bucket"], run_id, BASELINE_VERSION, WORKING_VERSION)
    log_event("core_ops.workspace_snapshot", run_id=run_id, files=copied, frm=BASELINE_VERSION, to=WORKING_VERSION)
    return {"run_id": str(run_id), "files": copied}


def junit_filename(iteration: int) -> str:
    return "verify.xml" if iteration == 0 else f"verify_iter{iteration}.xml"


def prepare_sandbox(event: dict[str, Any], s3_resource: Any) -> dict[str, str]:
    run_id = event["run_id"]
    handoff = prepare_sandbox_io(
        s3_resource, event["workspaces_bucket"], run_id, WORKING_VERSION, junit_filename(int(event.get("iteration", 0)))
    )
    log_event("core_ops.sandbox_prepared", run_id=run_id, junit_key=handoff["junit_key"])
    return handoff
