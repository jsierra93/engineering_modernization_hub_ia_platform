"""Creates the runs and events tables inside moto for unit tests; production tables come from Terraform."""

from __future__ import annotations

from typing import Any

from core_py.persistence import DEFAULT_EVENTS_TABLE, DEFAULT_RUNS_TABLE, GSI_REQUESTED_BY


def create_tables(
    resource: Any,
    runs_table_name: str = DEFAULT_RUNS_TABLE,
    events_table_name: str = DEFAULT_EVENTS_TABLE,
) -> None:
    resource.create_table(
        TableName=runs_table_name,
        KeySchema=[{"AttributeName": "run_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "run_id", "AttributeType": "S"},
            {"AttributeName": "requested_by", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": GSI_REQUESTED_BY,
                "KeySchema": [{"AttributeName": "requested_by", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5,
                },
            },
        ],
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    ).wait_until_exists()

    resource.create_table(
        TableName=events_table_name,
        KeySchema=[
            {"AttributeName": "run_id", "KeyType": "HASH"},
            {"AttributeName": "seq", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "run_id", "AttributeType": "S"},
            {"AttributeName": "seq", "AttributeType": "N"},
        ],
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    ).wait_until_exists()
