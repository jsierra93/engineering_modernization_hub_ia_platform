"""Lambda entrypoint: builds the agent for one phase, runs it and returns the result, cost and denials.
Never writes a verdict or calls SendTaskSuccess; core_ops applies the cost and decides.
"""

from __future__ import annotations

import json
import os
from typing import Any

from core_py import ModelRole, estimate_cost_usd, log_event, resolve_scope
from core_py.constants import BASELINE_VERSION, WORKING_VERSION, WORKSPACE_BUCKET_ENV

from agent_phase.agent_builder import build_agent
from agent_phase.fetch_doc_client import make_fetch_doc_fn
from agent_phase.guardrail import Guardrail, UntrustedContentBlocked
from agent_phase.phases import run_discovery_plan, run_fix, run_implement
from agent_phase.sandbox_handoff import copy_version, repackage_workspace_for_sandbox
from agent_phase.strategy_lookup import get_strategy_manifest
from agent_phase.workspace import S3Workspace

FETCH_DOC_FUNCTION_NAME_ENV = "MODHUB_FETCH_DOC_FUNCTION_NAME"


class UnknownPhaseError(Exception):
    pass


class PhaseProducedNothingError(Exception):
    pass


def _run(
    event: dict[str, Any],
    *,
    s3_resource: Any,
    lambda_client: Any,
    build_agent_fn=build_agent,
) -> dict[str, Any]:
    run_id = event["run_id"]
    phase = event["phase"]
    strategy_id = event["strategy_id"]

    manifest = get_strategy_manifest(strategy_id)
    bucket = os.environ[WORKSPACE_BUCKET_ENV]
    workspace_version = BASELINE_VERSION if phase == "discovery_plan" else WORKING_VERSION
    workspace = S3Workspace(s3_resource, bucket=bucket, run_id=run_id, version=workspace_version)
    fetch_doc_fn = make_fetch_doc_fn(lambda_client, os.environ[FETCH_DOC_FUNCTION_NAME_ENV])

    denials: list[dict[str, Any]] = []

    def on_deny(denial):
        denials.append({"tool_name": denial.tool_name, "reason": denial.reason, "attempted_path": denial.attempted_path})

    def on_block(source: str):
        denials.append({"tool_name": "guardrail", "reason": "prompt_attack_filter", "attempted_path": source})
        log_event("agent_phase.guardrail_blocked", run_id=run_id, phase=phase, source=source)

    guardrail = Guardrail.from_env()

    scope = resolve_scope(
        manifest.writable_paths,
        manifest.excluded_paths,
        event.get("excluded_paths") or [],
    )

    common_kwargs = dict(
        workspace=workspace,
        fetch_doc_fn=fetch_doc_fn,
        writable_paths=scope.writable_paths,
        excluded_paths=scope.excluded_paths,
        on_deny=on_deny,
        guardrail=guardrail,
        on_block=on_block,
    )

    handoff: dict[str, Any] = {}

    if phase == "discovery_plan":
        agent = build_agent_fn(
            role=ModelRole.ANALYSIS,
            max_tokens=manifest.model_limits.analysis_max_tokens,
            include_write_tool=False,
            **common_kwargs,
        )
        result = run_discovery_plan(agent, objetivo=event["objetivo"], strategy_summary=manifest.title)

    elif phase == "implement":
        agent = build_agent_fn(role=ModelRole.CODE, max_tokens=manifest.model_limits.code_max_tokens, **common_kwargs)
        from agent_phase.schemas import DiscoveryPlan

        plan = DiscoveryPlan.model_validate(event["plan"])
        copied = copy_version(s3_resource, bucket, run_id, BASELINE_VERSION, WORKING_VERSION)
        log_event("agent_phase.workspace_snapshot", run_id=run_id, files=copied,
                  frm=BASELINE_VERSION, to=WORKING_VERSION)
        result = run_implement(agent, plan=plan)
        handoff = repackage_workspace_for_sandbox(
            s3_resource, bucket, run_id, junit_filename="verify.xml", version=WORKING_VERSION
        )

    elif phase == "fix":
        agent = build_agent_fn(role=ModelRole.CODE, max_tokens=manifest.model_limits.code_max_tokens, **common_kwargs)
        junit_failure_excerpt = (
            s3_resource.Object(bucket, event["junit_key"]).get()["Body"].read().decode("utf-8", errors="replace")
        )
        if guardrail is not None:
            try:
                guardrail.screen(junit_failure_excerpt, source="junit:verify")
            except UntrustedContentBlocked:
                on_block("junit:verify")
                junit_failure_excerpt = "(test output withheld: blocked by the platform guardrail)"
        result = run_fix(
            agent,
            junit_failure_excerpt=junit_failure_excerpt,
            iteration=event["iteration"],
            max_iterations=event["max_iterations"],
        )
        handoff = repackage_workspace_for_sandbox(
            s3_resource, bucket, run_id, junit_filename=f"verify_iter{event['iteration']}.xml",
            version=WORKING_VERSION,
        )

    else:
        raise UnknownPhaseError(f"phase {phase!r} is not implemented")

    usage = agent.event_loop_metrics.accumulated_usage
    if usage["inputTokens"] == 0 and usage["outputTokens"] == 0:
        raise PhaseProducedNothingError(f"phase {phase!r} consumed no tokens -- the model was never reached")

    cost_usd = estimate_cost_usd(
        agent.model.get_config()["model_id"],
        usage["inputTokens"],
        usage["outputTokens"],
    )

    log_event(
        "agent_phase.completed",
        run_id=run_id,
        phase=phase,
        model_id=agent.model.get_config()["model_id"],
        input_tokens=usage["inputTokens"],
        output_tokens=usage["outputTokens"],
        cost_usd=cost_usd,
        denials=len(denials),
    )

    response = {
        "run_id": run_id,
        "phase": phase,
        "model_id": agent.model.get_config()["model_id"],
        "result": result.model_dump(mode="json"),
        "denials": denials,
        "cost_usd": cost_usd,
        **handoff,
    }

    _persist_phase_trail(s3_resource, bucket, run_id, phase, event, response)
    return response


def _persist_phase_trail(
    s3_resource: Any,
    bucket: str,
    run_id: str,
    phase: str,
    phase_input: dict[str, Any],
    phase_output: dict[str, Any],
) -> None:
    trail = {
        "phase": phase,
        "input": phase_input,
        "output": {key: value for key, value in phase_output.items() if key != "result"},
        "result": phase_output.get("result"),
    }
    try:
        s3_resource.Object(bucket, f"ws/{run_id}/phases/{phase}.json").put(
            Body=json.dumps(trail, default=str).encode("utf-8"),
            ContentType="application/json",
        )
    except Exception as exc:  # noqa: BLE001 - audit trail, never a verdict input
        log_event("agent_phase.trail_write_failed", run_id=run_id, phase=phase, error=str(exc)[:200])


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    import boto3

    s3_resource = boto3.resource("s3")
    lambda_client = boto3.client("lambda")
    return _run(event, s3_resource=s3_resource, lambda_client=lambda_client)
