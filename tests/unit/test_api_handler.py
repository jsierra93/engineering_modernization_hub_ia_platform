"""Task 1.6: mock DynamoDB (moto) and Step Functions start_execution
(unittest.mock), and assert a run can be created and read back with the
right shape via the lambda api handler.
"""

from __future__ import annotations

import io
import json
import time
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

from api.handler import create_run, get_run, handle_approval, list_runs
from core_py.models import Restricciones, Run, RunStatus
from core_py.persistence import RunsTable, create_tables


@pytest.fixture()
def dynamodb_resource():
    with mock_aws():
        yield boto3.resource("dynamodb", region_name="us-east-1")


@pytest.fixture()
def runs_table(dynamodb_resource):
    create_tables(dynamodb_resource)
    return RunsTable(resource=dynamodb_resource)


@pytest.fixture()
def sfn_client():
    client = MagicMock()
    client.start_execution.return_value = {"executionArn": "arn:aws:states:local:000000000000:execution:modhub-stub:test"}
    return client


@pytest.fixture()
def bedrock_client():
    """Always resolves to the one real registered strategy
    (python-pydantic-v2) -- create_run's tests aren't exercising the
    resolver itself (see test_resolver.py for that), just that create_run
    wires its result into the created Run."""
    client = MagicMock()

    def _invoke_model(**kwargs):
        body = json.dumps(
            {"content": [{"text": json.dumps({"strategy_id": "python-pydantic-v2", "confidence": 0.95})}]}
        ).encode("utf-8")
        return {"body": io.BytesIO(body)}

    client.invoke_model.side_effect = _invoke_model
    return client


def _create_run_event(**body_overrides) -> dict:
    body = {
        "repo": "https://github.com/example/demo",
        "commit": "a" * 40,
        "objetivo": "Migrate to Pydantic v2",
        "max_usd": 5.0,
        "max_iterations": 3,
        "max_minutes": 20,
    }
    body.update(body_overrides)
    return {
        "headers": {"x-requested-by": "jorgesierra93@gmail.com"},
        "body": json.dumps(body),
    }


def test_create_run_returns_201_with_expected_shape(runs_table, sfn_client, bedrock_client):
    response = create_run(_create_run_event(), runs_table, sfn_client, bedrock_client)

    assert response["statusCode"] == 201
    payload = json.loads(response["body"])

    assert "run_id" in payload
    assert payload["status"] == "PENDING"
    assert payload["resolved_strategy"]["id"] == "python-pydantic-v2"
    assert payload["requested_by"] == "jorgesierra93@gmail.com"
    assert "created_at" in payload

    sfn_client.start_execution.assert_called_once()


def test_create_run_persists_run_that_get_run_can_read_back(runs_table, sfn_client, bedrock_client):
    create_response = create_run(_create_run_event(), runs_table, sfn_client, bedrock_client)
    run_id = json.loads(create_response["body"])["run_id"]

    get_response = get_run({"pathParameters": {"run_id": run_id}}, runs_table)

    assert get_response["statusCode"] == 200
    run_payload = json.loads(get_response["body"])
    assert run_payload["run_id"] == run_id
    assert run_payload["repo"] == "https://github.com/example/demo"
    assert run_payload["status"] == "PENDING"


def test_get_run_returns_404_for_unknown_id(runs_table):
    response = get_run(
        {"pathParameters": {"run_id": "00000000-0000-0000-0000-000000000000"}},
        runs_table,
    )
    assert response["statusCode"] == 404
    payload = json.loads(response["body"])
    assert payload["code"] == "RUN_NOT_FOUND"


def test_create_run_missing_fields_returns_422(runs_table, sfn_client, bedrock_client):
    event = _create_run_event()
    body = json.loads(event["body"])
    del body["objetivo"]
    event["body"] = json.dumps(body)

    response = create_run(event, runs_table, sfn_client, bedrock_client)

    assert response["statusCode"] == 422
    sfn_client.start_execution.assert_not_called()


def test_create_run_no_strategy_match_returns_422(runs_table, sfn_client):
    no_match_client = MagicMock()
    no_match_client.invoke_model.return_value = {
        "body": io.BytesIO(json.dumps({"content": [{"text": json.dumps({"strategy_id": None, "confidence": 0.0})}]}).encode("utf-8"))
    }

    response = create_run(_create_run_event(), runs_table, sfn_client, no_match_client)

    assert response["statusCode"] == 422
    payload = json.loads(response["body"])
    assert payload["code"] == "NO_STRATEGY_MATCH"
    sfn_client.start_execution.assert_not_called()


def test_create_run_dev_strategy_bypass_skips_bedrock(runs_table, sfn_client, monkeypatch):
    """MODHUB_DEV_STRATEGY_ID (local-dev only, see infrastructure/envs/local)
    skips resolve_strategy/Bedrock entirely -- Floci doesn't emulate real
    model inference, so this is what lets FetchRepo/Baseline stay
    exercisable there."""
    monkeypatch.setenv("MODHUB_DEV_STRATEGY_ID", "python-pydantic-v2")
    unused_bedrock_client = MagicMock()

    response = create_run(_create_run_event(), runs_table, sfn_client, unused_bedrock_client)

    assert response["statusCode"] == 201
    payload = json.loads(response["body"])
    assert payload["resolved_strategy"]["id"] == "python-pydantic-v2"
    assert payload["resolved_strategy"]["match_confidence"] == 1.0
    unused_bedrock_client.invoke_model.assert_not_called()


def test_create_run_dev_strategy_bypass_misconfigured_returns_500(runs_table, sfn_client, monkeypatch):
    monkeypatch.setenv("MODHUB_DEV_STRATEGY_ID", "not-a-real-strategy")

    response = create_run(_create_run_event(), runs_table, sfn_client, MagicMock())

    assert response["statusCode"] == 500
    payload = json.loads(response["body"])
    assert payload["code"] == "DEV_STRATEGY_MISCONFIGURED"


def test_list_runs_defaults_to_callers_own_runs(runs_table, sfn_client, bedrock_client):
    create_run(_create_run_event(), runs_table, sfn_client, bedrock_client)
    create_run(_create_run_event(), runs_table, sfn_client, bedrock_client)

    # A run belonging to someone else must not show up.
    other_event = _create_run_event()
    other_event["headers"] = {"x-requested-by": "someone-else"}
    create_run(other_event, runs_table, sfn_client, bedrock_client)

    response = list_runs(
        {"headers": {"x-requested-by": "jorgesierra93@gmail.com"}, "queryStringParameters": None},
        runs_table,
    )

    assert response["statusCode"] == 200
    items = json.loads(response["body"])["items"]
    assert len(items) == 2
    assert all(item["requested_by"] == "jorgesierra93@gmail.com" for item in items)
    assert all("task_token" not in item for item in items)


def test_list_runs_filters_by_status(runs_table, sfn_client):
    run_a = _awaiting_approval_run(runs_table, status=RunStatus.AWAITING_APPROVAL)
    run_b = _awaiting_approval_run(runs_table, run_id="22222222-2222-2222-2222-222222222222", status=RunStatus.RUNNING)

    response = list_runs(
        {"headers": {"x-requested-by": "jorgesierra93@gmail.com"}, "queryStringParameters": {"status": "AWAITING_APPROVAL"}},
        runs_table,
    )

    items = json.loads(response["body"])["items"]
    run_ids = {item["run_id"] for item in items}
    assert str(run_a.run_id) in run_ids
    assert str(run_b.run_id) not in run_ids


def _awaiting_approval_run(runs_table, **overrides) -> Run:
    defaults = dict(
        repo="https://github.com/example/demo",
        commit="a" * 40,
        objetivo="Migrate to Pydantic v2",
        requested_by="jorgesierra93@gmail.com",
        strategy_id="python-pydantic-v2",
        strategy_version="1.0.0",
        max_usd=5.0,
        max_iterations=3,
        max_minutes=20,
        status=RunStatus.AWAITING_APPROVAL,
        plan_hash="hash-1",
        task_token="fake-task-token",
        restricciones=Restricciones(),
    )
    defaults.update(overrides)
    run = Run(**defaults)
    runs_table.put(run)
    return run


def _approval_event(run_id, **body_overrides) -> dict:
    body = {"decision": "approve", "plan_hash": "hash-1"}
    body.update(body_overrides)
    return {
        "pathParameters": {"run_id": str(run_id)},
        "headers": {"x-requested-by": "jorgesierra93@gmail.com"},
        "body": json.dumps(body),
    }


def test_handle_approval_approve_transitions_to_running_and_sends_task_success(runs_table, sfn_client):
    run = _awaiting_approval_run(runs_table)

    response = handle_approval(_approval_event(run.run_id), runs_table, sfn_client)

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    assert payload["status"] == "RUNNING"
    assert "task_token" not in payload
    assert runs_table.get(run.run_id).status == RunStatus.RUNNING
    sfn_client.send_task_success.assert_called_once()
    sfn_client.send_task_failure.assert_not_called()


def test_handle_approval_reject_transitions_to_cancelado_and_sends_task_failure(runs_table, sfn_client):
    run = _awaiting_approval_run(runs_table)

    response = handle_approval(
        _approval_event(run.run_id, decision="reject", reason="not needed"), runs_table, sfn_client
    )

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    assert payload["status"] == "CANCELADO"
    assert runs_table.get(run.run_id).status == RunStatus.CANCELADO
    sfn_client.send_task_failure.assert_called_once()
    sfn_client.send_task_success.assert_not_called()


def test_handle_approval_wrong_requester_returns_403(runs_table, sfn_client):
    run = _awaiting_approval_run(runs_table)

    event = _approval_event(run.run_id)
    event["headers"] = {"x-requested-by": "someone-else"}

    response = handle_approval(event, runs_table, sfn_client)

    assert response["statusCode"] == 403
    assert runs_table.get(run.run_id).status == RunStatus.AWAITING_APPROVAL
    sfn_client.send_task_success.assert_not_called()


def test_handle_approval_stale_plan_hash_returns_409(runs_table, sfn_client):
    run = _awaiting_approval_run(runs_table)

    response = handle_approval(
        _approval_event(run.run_id, plan_hash="stale-hash"), runs_table, sfn_client
    )

    assert response["statusCode"] == 409
    assert runs_table.get(run.run_id).status == RunStatus.AWAITING_APPROVAL


def test_handle_approval_stale_auth_time_returns_401(runs_table, sfn_client):
    """CLAUDE.md invariant #7: 'auth is recent' -- a validly-signed JWT
    whose auth_time is old must still be rejected."""
    run = _awaiting_approval_run(runs_table)

    event = _approval_event(run.run_id)
    event["headers"] = {}
    event["requestContext"] = {
        "authorizer": {
            "jwt": {"claims": {"sub": "jorgesierra93@gmail.com", "auth_time": str(int(time.time()) - 3600)}}
        }
    }

    response = handle_approval(event, runs_table, sfn_client)

    assert response["statusCode"] == 401
    payload = json.loads(response["body"])
    assert payload["code"] == "AUTH_NOT_RECENT"
    assert runs_table.get(run.run_id).status == RunStatus.AWAITING_APPROVAL


def test_handle_approval_recent_auth_time_succeeds(runs_table, sfn_client):
    run = _awaiting_approval_run(runs_table)

    event = _approval_event(run.run_id)
    event["headers"] = {}
    event["requestContext"] = {
        "authorizer": {
            "jwt": {"claims": {"sub": "jorgesierra93@gmail.com", "auth_time": str(int(time.time()) - 10)}}
        }
    }

    response = handle_approval(event, runs_table, sfn_client)

    assert response["statusCode"] == 200


def test_handle_approval_unknown_run_returns_404(runs_table, sfn_client):
    response = handle_approval(
        _approval_event("00000000-0000-0000-0000-000000000000"), runs_table, sfn_client
    )
    assert response["statusCode"] == 404


def test_handle_approval_missing_decision_returns_422(runs_table, sfn_client):
    run = _awaiting_approval_run(runs_table)

    event = _approval_event(run.run_id)
    event["body"] = json.dumps({"plan_hash": "hash-1"})

    response = handle_approval(event, runs_table, sfn_client)

    assert response["statusCode"] == 422
