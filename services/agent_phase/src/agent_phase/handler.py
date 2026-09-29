"""Lambda entrypoint: builds the agent for one phase, runs it and returns the result, cost and denials.
Never writes a verdict or calls SendTaskSuccess; core_ops applies the cost and decides.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from core_py import ModelRole, estimate_cost_usd, log_event, rate_for, resolve_model_id, resolve_scope
from core_py.constants import BASELINE_VERSION, WORKING_VERSION, WORKSPACE_BUCKET_ENV

from agent_phase.agent_builder import build_agent
from agent_phase.fetch_doc_client import make_fetch_doc_fn
from agent_phase.guardrail import Guardrail, UntrustedContentBlocked
from agent_phase.phases import run_discovery_plan, run_fix, run_implement
from agent_phase.schemas import DiscoveryPlan
from agent_phase.sandbox_handoff import copy_version, repackage_workspace_for_sandbox
from agent_phase.strategy_lookup import get_strategy_manifest
from agent_phase.workspace import S3Workspace

FETCH_DOC_FUNCTION_NAME_ENV = "MODHUB_FETCH_DOC_FUNCTION_NAME"


class UnknownPhaseError(Exception):
    pass


class PhaseProducedNothingError(Exception):
    pass


@dataclass
class _PhaseContext:
    event: dict[str, Any]
    run_id: str
    phase: str
    manifest: Any
    bucket: str
    s3_resource: Any
    guardrail: Guardrail | None
    build_agent_fn: Any
    agent_kwargs: dict[str, Any]
    on_block: Any

    def build_agent(self, role: ModelRole, max_tokens: int, **extra: Any):
        return self.build_agent_fn(role=role, max_tokens=max_tokens, **extra, **self.agent_kwargs)


def _phase_discovery_plan(ctx: _PhaseContext):
    agent = ctx.build_agent(
        ModelRole.ANALYSIS, ctx.manifest.model_limits.analysis_max_tokens, include_write_tool=False
    )
    result = run_discovery_plan(agent, objetivo=ctx.event["objetivo"], strategy_summary=ctx.manifest.title)
    return agent, result, {}


def _phase_implement(ctx: _PhaseContext):
    agent = ctx.build_agent(ModelRole.CODE, ctx.manifest.model_limits.code_max_tokens)
    plan = DiscoveryPlan.model_validate(ctx.event["plan"])
    copied = copy_version(ctx.s3_resource, ctx.bucket, ctx.run_id, BASELINE_VERSION, WORKING_VERSION)
    log_event("agent_phase.workspace_snapshot", run_id=ctx.run_id, files=copied,
              frm=BASELINE_VERSION, to=WORKING_VERSION)
    result = run_implement(agent, plan=plan)
    handoff = repackage_workspace_for_sandbox(
        ctx.s3_resource, ctx.bucket, ctx.run_id, junit_filename="verify.xml", version=WORKING_VERSION
    )
    return agent, result, handoff


def _screened_junit_excerpt(ctx: _PhaseContext) -> str:
    excerpt = (
        ctx.s3_resource.Object(ctx.bucket, ctx.event["junit_key"]).get()["Body"].read().decode("utf-8", errors="replace")
    )
    if ctx.guardrail is not None:
        try:
            ctx.guardrail.screen(excerpt, source="junit:verify")
        except UntrustedContentBlocked:
            ctx.on_block("junit:verify")
            return "(test output withheld: blocked by the platform guardrail)"
    return excerpt


def _phase_fix(ctx: _PhaseContext):
    agent = ctx.build_agent(ModelRole.CODE, ctx.manifest.model_limits.code_max_tokens)
    result = run_fix(
        agent,
        junit_failure_excerpt=_screened_junit_excerpt(ctx),
        iteration=ctx.event["iteration"],
        max_iterations=ctx.event["max_iterations"],
    )
    handoff = repackage_workspace_for_sandbox(
        ctx.s3_resource, ctx.bucket, ctx.run_id, junit_filename=f"verify_iter{ctx.event['iteration']}.xml",
        version=WORKING_VERSION,
    )
    return agent, result, handoff


_PHASES = {
    "discovery_plan": _phase_discovery_plan,
    "implement": _phase_implement,
    "fix": _phase_fix,
}


def _cost_of(agent: Any, phase: str) -> tuple[str, dict[str, int], float]:
    usage = agent.event_loop_metrics.accumulated_usage
    if usage["inputTokens"] == 0 and usage["outputTokens"] == 0:
        raise PhaseProducedNothingError(f"phase {phase!r} consumed no tokens -- the model was never reached")
    model_id = agent.model.get_config()["model_id"]
    return model_id, usage, estimate_cost_usd(model_id, usage["inputTokens"], usage["outputTokens"])


def _run(
    event: dict[str, Any],
    *,
    s3_resource: Any,
    lambda_client: Any,
    build_agent_fn=build_agent,
) -> dict[str, Any]:
    run_id = event["run_id"]
    phase = event["phase"]

    manifest = get_strategy_manifest(event["strategy_id"])
    for role in ModelRole:
        rate_for(resolve_model_id(role))
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
    scope = resolve_scope(manifest.writable_paths, manifest.excluded_paths, event.get("excluded_paths") or [])
    ctx = _PhaseContext(
        event=event,
        run_id=run_id,
        phase=phase,
        manifest=manifest,
        bucket=bucket,
        s3_resource=s3_resource,
        guardrail=guardrail,
        build_agent_fn=build_agent_fn,
        agent_kwargs=dict(
            workspace=workspace,
            fetch_doc_fn=fetch_doc_fn,
            writable_paths=scope.writable_paths,
            excluded_paths=scope.excluded_paths,
            on_deny=on_deny,
            guardrail=guardrail,
            on_block=on_block,
        ),
        on_block=on_block,
    )

    if phase not in _PHASES:
        raise UnknownPhaseError(f"phase {phase!r} is not implemented")
    agent, result, handoff = _PHASES[phase](ctx)

    model_id, usage, cost_usd = _cost_of(agent, phase)
    log_event(
        "agent_phase.completed",
        run_id=run_id,
        phase=phase,
        model_id=model_id,
        input_tokens=usage["inputTokens"],
        output_tokens=usage["outputTokens"],
        cost_usd=cost_usd,
        denials=len(denials),
    )

    response = {
        "run_id": run_id,
        "phase": phase,
        "model_id": model_id,
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
    trail_name = f"{phase}_{phase_input['iteration']}" if phase == "fix" and "iteration" in phase_input else phase
    try:
        s3_resource.Object(bucket, f"ws/{run_id}/phases/{trail_name}.json").put(
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
