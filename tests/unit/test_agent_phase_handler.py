"""Task 3.3: the full handler dispatch, proven without Bedrock -- a fake
`build_agent_fn` stands in, matching PLAN.md 3.3's own scope exactly
("cableado de fases con salida mock fija, solo para probar el cableado").
Real S3 via moto (this Lambda has real, scoped IAM, unlike the sandbox)."""

from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_aws

from agent_phase.handler import UnknownPhaseError, _run
from agent_phase.schemas import DiscoveryPlan, FixAttempt, ImplementationResult, PlannedFileChange

BUCKET = "modhub-workspaces"


@pytest.fixture()
def s3_resource(monkeypatch):
    monkeypatch.setenv("MODHUB_WORKSPACE_BUCKET", BUCKET)
    monkeypatch.setenv("MODHUB_FETCH_DOC_FUNCTION_NAME", "modhub-fetch-doc")
    with mock_aws():
        resource = boto3.resource("s3", region_name="us-east-1")
        resource.create_bucket(Bucket=BUCKET)
        yield resource


class _FakeLambdaClient:
    def invoke(self, *, FunctionName, Payload):
        raise AssertionError("fetch_doc should not be invoked by this test -- the fake agent never calls the tool")


class _FakeAgent:
    def __init__(self, response):
        self.response = response

    def structured_output(self, output_model, prompt=None):
        return self.response


def _fake_build_agent_fn(response):
    def build(**kwargs):
        return _FakeAgent(response)

    return build


def test_discovery_plan_phase_returns_the_agents_plan_as_json(s3_resource):
    plan = DiscoveryPlan(
        viable=True,
        viability_reason="pydantic<2 detected",
        summary="Migrate to Pydantic v2",
        planned_changes=[PlannedFileChange(path="src/models.py", reason="uses @validator")],
        sources=["https://docs.pydantic.dev/latest/migration/"],
    )

    result = _run(
        {"run_id": "run-1", "phase": "discovery_plan", "strategy_id": "python-pydantic-v2", "objetivo": "migrar pydantic v1 a v2"},
        s3_resource=s3_resource,
        lambda_client=_FakeLambdaClient(),
        build_agent_fn=_fake_build_agent_fn(plan),
    )

    assert result["run_id"] == "run-1"
    assert result["phase"] == "discovery_plan"
    assert result["result"]["summary"] == "Migrate to Pydantic v2"
    assert result["result"]["sources"] == ["https://docs.pydantic.dev/latest/migration/"]
    assert result["denials"] == []


def test_implement_phase_reads_the_plan_from_the_event(s3_resource):
    impl = ImplementationResult(files_changed=[], notes="done")
    plan_dict = DiscoveryPlan(viable=True, viability_reason="x", summary="x").model_dump(mode="json")

    result = _run(
        {"run_id": "run-2", "phase": "implement", "strategy_id": "python-pydantic-v2", "plan": plan_dict},
        s3_resource=s3_resource,
        lambda_client=_FakeLambdaClient(),
        build_agent_fn=_fake_build_agent_fn(impl),
    )

    assert result["result"]["notes"] == "done"
    # Verify (a different phase, invoked next by the ASL) needs these --
    # the sandbox has zero AWS credentials and can't fetch S3 itself.
    assert "workspace_get_url" in result
    assert "junit_put_url" in result
    assert result["junit_key"] == "ws/run-2/junit/verify.xml"


def test_fix_phase_returns_the_fix_attempt(s3_resource):
    fix = FixAttempt(root_cause="wrong validator syntax", fix_summary="updated to field_validator", confident=True)
    s3_resource.Bucket(BUCKET).put_object(Key="ws/run-3/junit/verify.xml", Body=b"AssertionError")

    result = _run(
        {
            "run_id": "run-3",
            "phase": "fix",
            "strategy_id": "python-pydantic-v2",
            "junit_key": "ws/run-3/junit/verify.xml",
            "iteration": 1,
            "max_iterations": 3,
        },
        s3_resource=s3_resource,
        lambda_client=_FakeLambdaClient(),
        build_agent_fn=_fake_build_agent_fn(fix),
    )

    assert result["result"]["confident"] is True


def test_unknown_phase_raises_loudly(s3_resource):
    with pytest.raises(UnknownPhaseError):
        _run(
            {"run_id": "run-4", "phase": "not_a_real_phase", "strategy_id": "python-pydantic-v2"},
            s3_resource=s3_resource,
            lambda_client=_FakeLambdaClient(),
            build_agent_fn=_fake_build_agent_fn(None),
        )


def test_unknown_strategy_raises_loudly(s3_resource):
    with pytest.raises(ValueError, match="no registered strategy"):
        _run(
            {"run_id": "run-5", "phase": "discovery_plan", "strategy_id": "does-not-exist", "objetivo": "x"},
            s3_resource=s3_resource,
            lambda_client=_FakeLambdaClient(),
            build_agent_fn=_fake_build_agent_fn(None),
        )


def test_denials_from_the_gate_are_collected_and_returned(s3_resource, monkeypatch):
    """Confirms the on_deny wiring set up in _run actually surfaces
    denials in the response -- important because that's what a real
    caller would persist as SecurityBlocked events."""

    plan = DiscoveryPlan(viable=True, viability_reason="x", summary="x")

    def build_agent_that_denies(*, on_deny, **kwargs):
        from agent_phase.policy_gate import DenialEvent

        on_deny(DenialEvent(tool_name="write_file", reason="path escapes writable_paths", attempted_path="../evil.py"))
        return _FakeAgent(plan)

    result = _run(
        {"run_id": "run-6", "phase": "discovery_plan", "strategy_id": "python-pydantic-v2", "objetivo": "x"},
        s3_resource=s3_resource,
        lambda_client=_FakeLambdaClient(),
        build_agent_fn=build_agent_that_denies,
    )

    assert result["denials"] == [
        {"tool_name": "write_file", "reason": "path escapes writable_paths", "attempted_path": "../evil.py"}
    ]
