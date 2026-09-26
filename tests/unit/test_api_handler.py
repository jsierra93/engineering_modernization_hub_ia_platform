"""Task 1.6: mock DynamoDB (moto) and Step Functions start_execution
(unittest.mock), and assert a run can be created and read back with the
right shape via the lambda api handler.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

from api.handler import create_run, get_run
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


def test_create_run_returns_201_with_expected_shape(runs_table, sfn_client):
    response = create_run(_create_run_event(), runs_table, sfn_client)

    assert response["statusCode"] == 201
    payload = json.loads(response["body"])

    assert "run_id" in payload
    assert payload["status"] == "PENDING"
    assert payload["resolved_strategy"]["id"] == "python-pydantic-v2"
    assert payload["requested_by"] == "jorgesierra93@gmail.com"
    assert "created_at" in payload

    sfn_client.start_execution.assert_called_once()


def test_create_run_persists_run_that_get_run_can_read_back(runs_table, sfn_client):
    create_response = create_run(_create_run_event(), runs_table, sfn_client)
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


def test_create_run_missing_fields_returns_422(runs_table, sfn_client):
    event = _create_run_event()
    body = json.loads(event["body"])
    del body["objetivo"]
    event["body"] = json.dumps(body)

    response = create_run(event, runs_table, sfn_client)

    assert response["statusCode"] == 422
    sfn_client.start_execution.assert_not_called()
