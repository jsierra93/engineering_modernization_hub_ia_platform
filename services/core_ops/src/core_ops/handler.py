"""Lambda handler for `core_ops` -- the deterministic core, invoked at
each checkpoint the ASL passes through. Never imports Bedrock (CLAUDE.md
invariant #1, enforced structurally: nothing in this package or its
dependencies pulls in `core_py.bedrock_models` or a Bedrock client).

Two actions, matching the two moments the design calls "checkpoints":
  - `record_plan`: right after DiscoveryPlan. Computes plan_hash from the
    agent's proposed plan (never the agent's own claim of a hash) and
    moves the run to AWAITING_APPROVAL.
  - `compute_verdict`: after Baseline or after Verify. Parses real JUnit,
    checks suite integrity, evaluates the five-state table, and persists
    the result. This is the one place a run's `status` becomes final.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core_py.models import RunStatus
from core_py.observability import log_event
from core_py.scope import resolve_scope
from core_py.models import Event
from core_py.persistence import EventsTable, RunsTable

from core_ops.diff import compute_diff
from core_ops.strategy_lookup import get_strategy_manifest
from core_ops.plan_hash import compute_plan_hash
from core_ops.suite_integrity import JUnitSummary, check_suite_integrity, parse_junit
from core_ops.verdict import BudgetStatus, VerdictInputs, evaluate_verdict_with_reason

# CLAUDE.md's platform ceiling -- resolve_limits' own invariant check
# happens earlier (Fase 4's resolver); this handler only ever reads
# already-resolved limits off the Run record.


class UnknownActionError(Exception):
    """The ASL asked for an action this handler doesn't implement."""


def _record_task_token(event: dict[str, Any], runs_table: RunsTable) -> dict[str, Any]:
    """AwaitApproval (Fase 4, task 4.3) calls this via
    arn:aws:states:::lambda:invoke.waitForTaskToken -- the ASL passes its
    own task token here, and core_ops persists it on the Run so a much
    later, entirely separate Lambda invocation (POST /runs/{id}/approval)
    can retrieve it and call SendTaskSuccess/SendTaskFailure. This
    Task does NOT complete until that later call happens -- returning
    from this function does not resume the state machine."""

    run_id = event["run_id"]
    run = runs_table.get(run_id)
    if run is None:
        raise ValueError(f"no such run: {run_id}")

    run.task_token = event["task_token"]
    runs_table.put(run)

    return {"run_id": str(run_id), "recorded": True}


def _record_plan(event: dict[str, Any], runs_table: RunsTable) -> dict[str, Any]:
    run_id = event["run_id"]
    run = runs_table.get(run_id)
    if run is None:
        raise ValueError(f"no such run: {run_id}")

    plan_hash = compute_plan_hash(event["plan"])
    log_event("core_ops.plan_recorded", run_id=run_id, plan_hash=plan_hash)
    run.plan_hash = plan_hash
    run.plan = event["plan"]
    run.awaiting_approval_since = datetime.now(UTC)
    run.status = RunStatus.AWAITING_APPROVAL
    runs_table.put(run)

    return {"run_id": str(run_id), "plan_hash": plan_hash, "status": run.status.value}


def _resolve_junit_xml(event: dict[str, Any], *, key_field: str, xml_field: str, s3_resource: Any) -> str:
    """Real ASL usage passes an S3 key (core_ops already has
    `s3:GetObject` on `ws/*/junit/*` per its IAM scope -- reading it here
    is cheaper and more robust than threading potentially large XML text
    through Step Functions' own 256KB-per-state payload limit). Tests may
    pass the XML text directly via `xml_field` for simplicity -- both
    paths produce the same `JUnitSummary`."""

    if xml_field in event:
        return event[xml_field]
    bucket = event["workspaces_bucket"]
    key = event[key_field]
    return s3_resource.Object(bucket, key).get()["Body"].read().decode("utf-8", errors="replace")


def _persist_denials(run_id: str, denials: list[dict[str, Any]], events_table: EventsTable | None) -> None:
    """CLAUDE.md: "cada denegación queda en la tabla de eventos". The gate
    decides and agent_phase reports; agent_phase has no DynamoDB access, so
    writing them is core_ops' job."""

    if not denials or events_table is None:
        return

    base_seq = len(events_table.query_by_run_id(run_id))
    for offset, denial in enumerate(denials):
        events_table.append(
            Event(
                run_id=run_id,
                seq=base_seq + offset,
                type="SecurityBlocked",
                message=denial.get("reason"),
                data=denial,
            )
        )
        log_event("core_ops.security_blocked", run_id=run_id, **denial)


def _record_spend(
    event: dict[str, Any], runs_table: RunsTable, events_table: EventsTable | None = None
) -> dict[str, Any]:
    """Applies a Bedrock cost delta reported by agent_phase (which has no
    DynamoDB access itself) to the run's budget ledger, via the same
    atomic conditional update `add_spend` already provides (invariant #6).
    The spend is always recorded; whether it put the run over its limit is
    reported back so the ASL can stop before the next phase."""

    run_id = event["run_id"]
    run = runs_table.get(run_id)
    if run is None:
        raise ValueError(f"no such run: {run_id}")

    _persist_denials(run_id, event.get("denials") or [], events_table)

    phase, model_id = event.get("phase"), event.get("model_id")
    if phase and model_id and run.models_used.get(phase) != model_id:
        run.models_used[phase] = model_id
        # Before add_spend, whose atomic increment this put would otherwise
        # overwrite with the value read above.
        runs_table.put(run)

    spent_usd = runs_table.add_spend(run_id, event["delta_usd"])
    exhausted = spent_usd >= run.max_usd

    log_event(
        "core_ops.spend",
        run_id=run_id,
        delta_usd=event["delta_usd"],
        phase=phase,
        model_id=model_id,
        spent_usd=spent_usd,
        max_usd=run.max_usd,
        budget_exhausted=exhausted,
    )
    return {"run_id": str(run_id), "spent_usd": spent_usd, "budget_exhausted": exhausted}


def _record_terminal_failure(event: dict[str, Any], runs_table: RunsTable) -> dict[str, Any]:
    """Called by the ASL only when computing a verdict itself failed. Keeps
    a run from sitting in RUNNING forever, which is worse than a wrong
    verdict: it reads as still working."""

    run_id = event["run_id"]
    run = runs_table.get(run_id)
    if run is None:
        raise ValueError(f"no such run: {run_id}")

    run.status = RunStatus.FALLIDO_CONTROLADO
    runs_table.put(run)
    log_event("core_ops.terminal_failure", run_id=run_id, cause=str(event.get("cause"))[:300])
    return {"run_id": str(run_id), "status": run.status.value}


def _compute_verdict(event: dict[str, Any], runs_table: RunsTable, s3_resource: Any = None) -> dict[str, Any]:
    run_id = event["run_id"]
    run = runs_table.get(run_id)
    if run is None:
        raise ValueError(f"no such run: {run_id}")

    baseline_xml = _resolve_junit_xml(event, key_field="baseline_junit_key", xml_field="baseline_junit_xml", s3_resource=s3_resource)
    final_xml = _resolve_junit_xml(event, key_field="final_junit_key", xml_field="final_junit_xml", s3_resource=s3_resource)
    baseline: JUnitSummary = parse_junit(baseline_xml)
    final: JUnitSummary = parse_junit(final_xml)
    violation = check_suite_integrity(baseline, final)

    # The infeasible path never reaches RecordPlan -- it must not, since
    # that state also moves the run to AWAITING_APPROVAL, and there is
    # nothing to approve. But the plan is where the reasoning and the
    # sources live, so without this the run reports BLOQUEADO with an empty
    # narrative: the right verdict stripped of the evidence that
    # invariant #11 requires it to carry.
    if event.get("plan") and run.plan is None:
        run.plan = event["plan"]

    # The fix loop's real counter lives in the state machine ($.iteration);
    # nothing was copying it onto the run, so every report said "0/N"
    # however many corrections had actually run.
    if event.get("iteration") is not None:
        run.iterations_used = int(event["iteration"])

    bucket = event.get("workspaces_bucket")
    diff_text = ""
    if bucket and s3_resource is not None:
        try:
            diff_text, run.changed_paths = compute_diff(s3_resource, bucket, str(run_id))
            # The diff goes to S3, never into the run item. A DynamoDB item
            # tops out at 400 KB shared with the plan and the narrative, so
            # a large diff makes put_item raise -- after the verdict is
            # already computed, which the Catch then turns into
            # FALLIDO_CONTROLADO. The bigger a successful migration, the
            # likelier it would be reported as a failure.
            if diff_text:
                run.diff_key = f"ws/{run_id}/diff.patch"
                s3_resource.Object(bucket, run.diff_key).put(
                    Body=diff_text.encode("utf-8"), ContentType="text/x-patch"
                )
            log_event("core_ops.diff", run_id=run_id, changed_paths=run.changed_paths,
                      diff_chars=len(diff_text), diff_key=run.diff_key)
        except Exception as exc:  # noqa: BLE001
            log_event("core_ops.diff_failed", run_id=run_id, error=str(exc)[:300])

    # Invariant #4, verified rather than assumed: the core re-derives the
    # approved scope from the strategy manifest and the run's own
    # restrictions, then checks what actually changed against it. The gate
    # denies at write time; this catches anything that got through.
    escaped: list[str] = []
    if run.changed_paths:
        try:
            manifest = get_strategy_manifest(run.strategy_id)
            scope = resolve_scope(
                manifest.writable_paths,
                manifest.excluded_paths,
                run.restricciones.excluded_paths,
            )
            escaped = [p for p in run.changed_paths if not scope.allows(p)]
        except Exception as exc:  # noqa: BLE001
            log_event("core_ops.scope_check_failed", run_id=run_id, error=str(exc)[:300])

    if escaped:
        log_event("core_ops.diff_escaped_scope", run_id=run_id, paths=escaped)
        _persist_denials(
            str(run_id),
            [{"tool_name": "diff", "reason": "changed path outside approved scope", "attempted_path": p}
             for p in escaped],
            events_table,
        )


    elapsed_minutes = (
        (datetime.now(UTC) - run.created_at).total_seconds() - run.approval_wait_seconds
    ) / 60.0
    budget = BudgetStatus(
        spent_usd=run.spent_usd,
        max_usd=run.max_usd,
        elapsed_minutes=elapsed_minutes,
        max_minutes=run.max_minutes,
        iterations_used=run.iterations_used,
        max_iterations=run.max_iterations,
    )
    inputs = VerdictInputs(
        budget=budget,
        baseline_failed=event.get("baseline_failed", False),
        agent_concluded_infeasible=event.get("agent_concluded_infeasible", False),
        fix_iterations_exhausted_without_pass=event.get("fix_iterations_exhausted_without_pass", False),
        unrecoverable_error=event.get("unrecoverable_error", False),
        approval_timed_out=event.get("approval_timed_out", False),
        suite_violation=violation,
        checks=event.get("checks", {}),
        diff_within_writable_paths=not escaped,
        produced_changes=bool(run.changed_paths),
    )
    status, reason_code = evaluate_verdict_with_reason(inputs)
    run.reason_code = reason_code

    # Every input the verdict was computed from, so the decision is
    # auditable without re-running it (CLAUDE.md invariant #1/#10).
    log_event(
        "core_ops.verdict",
        run_id=run_id,
        status=status.value,
        spent_usd=run.spent_usd,
        max_usd=run.max_usd,
        elapsed_minutes=round(elapsed_minutes, 2),
        approval_wait_seconds=run.approval_wait_seconds,
        max_minutes=run.max_minutes,
        iterations_used=run.iterations_used,
        max_iterations=run.max_iterations,
        baseline_failed=inputs.baseline_failed,
        agent_concluded_infeasible=inputs.agent_concluded_infeasible,
        fix_iterations_exhausted=inputs.fix_iterations_exhausted_without_pass,
        unrecoverable_error=inputs.unrecoverable_error,
        suite_violation=violation,
        checks=inputs.checks,
        baseline_executed=baseline.executed,
        final_executed=final.executed,
    )

    run.status = status
    runs_table.put(run)

    return {
        "run_id": str(run_id),
        "status": status.value,
        "suite_violation": violation,
        "baseline": {"executed": baseline.executed, "passed": baseline.passed},
        "final": {"executed": final.executed, "passed": final.passed},
    }


def _run(
    event: dict[str, Any],
    *,
    runs_table: RunsTable,
    s3_resource: Any = None,
    events_table: EventsTable | None = None,
) -> dict[str, Any]:
    action = event["action"]
    if action == "record_plan":
        return _record_plan(event, runs_table)
    if action == "compute_verdict":
        return _compute_verdict(event, runs_table, s3_resource=s3_resource)
    if action == "record_task_token":
        return _record_task_token(event, runs_table)
    if action == "record_terminal_failure":
        return _record_terminal_failure(event, runs_table)
    if action == "record_spend":
        return _record_spend(event, runs_table, events_table)
    raise UnknownActionError(f"action {action!r} is not implemented")


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    import boto3

    resource = boto3.resource("dynamodb")
    return _run(
        event,
        runs_table=RunsTable(resource=resource),
        s3_resource=boto3.resource("s3"),
        events_table=EventsTable(resource=resource),
    )
