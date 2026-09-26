"""Thin DynamoDB access layer for the `runs` and `events` tables.

Determinístico zone (CLAUDE.md): this module never imports a Bedrock
client and never computes a verdict -- it only stores and retrieves what
core_ops and lambda api need.

Table shapes (mirrored by infrastructure/modules/persistence, owned by a
different workstream):

- `runs`: partition key `run_id`. GSI `gsi_status` (partition `status`),
  GSI `gsi_requested_by` (partition `requested_by`).
- `events`: partition key `run_id`, sort key `seq` (append-only).
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

import boto3
import boto3.dynamodb.conditions as conditions
from botocore.exceptions import ClientError

from core_py.models import Event, Run


class BudgetExceededError(Exception):
    """Raised by `RunsTable.add_spend` when applying a spend delta would
    push `spent_usd` past `max_usd`. Distinct from a generic
    `ClientError` so callers can catch exactly this and route the run to
    `PRESUPUESTO_AGOTADO` instead of treating it as an infra failure."""


class ApprovalConflictError(Exception):
    """Raised by `RunsTable.approve_or_reject` when the conditional update
    fails: the run isn't AWAITING_APPROVAL, `sub` doesn't match
    `requested_by`, or `plan_hash` is stale. The caller (services/api)
    maps this to a 409; a 403 identity mismatch is checked separately,
    before this method is even called, so the two cases stay
    distinguishable to the API client."""


def _floats_to_decimal(item: dict[str, Any]) -> dict[str, Any]:
    """DynamoDB's low-level type serializer rejects Python `float`
    outright ("use Decimal types instead"). Round-trip through JSON so
    every float in a (possibly nested) dict becomes a `Decimal`."""

    return json.loads(json.dumps(item), parse_float=Decimal)

DEFAULT_RUNS_TABLE = "modhub-runs"
DEFAULT_EVENTS_TABLE = "modhub-events"

GSI_STATUS = "gsi_status"
GSI_REQUESTED_BY = "gsi_requested_by"


def _run_to_item(run: Run) -> dict[str, Any]:
    item = run.model_dump(mode="json")
    item["run_id"] = str(run.run_id)
    return _floats_to_decimal(item)


def _item_to_run(item: dict[str, Any]) -> Run:
    return Run.model_validate(item)


def _event_to_item(event: Event) -> dict[str, Any]:
    item = event.model_dump(mode="json")
    item["run_id"] = str(event.run_id)
    return _floats_to_decimal(item)


def _item_to_event(item: dict[str, Any]) -> Event:
    return Event.model_validate(item)


class RunsTable:
    """Access to the `runs` table: put/get by primary key, query by GSI."""

    def __init__(
        self,
        table_name: str = DEFAULT_RUNS_TABLE,
        resource: Any | None = None,
    ) -> None:
        self._resource = resource or boto3.resource("dynamodb")
        self._table = self._resource.Table(table_name)

    def put(self, run: Run) -> None:
        self._table.put_item(Item=_run_to_item(run))

    def get(self, run_id: uuid.UUID | str) -> Run | None:
        resp = self._table.get_item(Key={"run_id": str(run_id)})
        item = resp.get("Item")
        return _item_to_run(item) if item else None

    def query_by_status(self, status: str) -> list[Run]:
        resp = self._table.query(
            IndexName=GSI_STATUS,
            KeyConditionExpression=conditions.Key("status").eq(status),
        )
        return [_item_to_run(item) for item in resp.get("Items", [])]

    def query_by_requested_by(self, requested_by: str) -> list[Run]:
        resp = self._table.query(
            IndexName=GSI_REQUESTED_BY,
            KeyConditionExpression=conditions.Key("requested_by").eq(
                requested_by
            ),
        )
        return [_item_to_run(item) for item in resp.get("Items", [])]

    def add_spend(self, run_id: uuid.UUID | str, delta: float, max_usd: float) -> None:
        """Atomically add `delta` to `spent_usd`, enforcing
        `spent_usd + delta <= max_usd` with a single conditional
        `update_item` -- never a read-then-write race (CLAUDE.md
        invariant #6).

        Raises `BudgetExceededError` if the condition fails (two
        concurrent/sequential calls that together would exceed
        `max_usd`), so the caller gets a specific, catchable exception
        rather than a bare `ClientError` leaking through.
        """

        delta_decimal = Decimal(str(delta))
        max_decimal = Decimal(str(max_usd))

        try:
            self._table.update_item(
                Key={"run_id": str(run_id)},
                UpdateExpression="SET spent_usd = spent_usd + :delta",
                ConditionExpression="spent_usd <= :max_minus_delta",
                ExpressionAttributeValues={
                    ":delta": delta_decimal,
                    ":max_minus_delta": max_decimal - delta_decimal,
                },
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise BudgetExceededError(
                    f"adding {delta} to run {run_id}'s spend would exceed "
                    f"max_usd={max_usd}"
                ) from exc
            raise

    def approve_or_reject(
        self, run_id: uuid.UUID | str, *, sub: str, plan_hash: str, new_status: str
    ) -> None:
        """The design's own "un solo update condicional": status transitions
        away from AWAITING_APPROVAL only if `sub == requested_by` AND the
        provided `plan_hash` matches exactly -- in one atomic DynamoDB
        write, never a read-then-write race between two people approving
        the same run at once. CLAUDE.md: "quien crea la solicitud es quien
        la aprueba," enforced here, not just in application logic that a
        second request could race past.

        Raises `ApprovalConflictError` if the condition fails -- wrong
        person, wrong state, or a stale plan_hash (the plan changed since
        the caller last fetched it). The caller (services/api) maps this
        to 403 (identity mismatch, checked again before calling this so
        the caller can tell that case apart from a stale hash/state) or
        409 (state/hash conflict).
        """

        try:
            self._table.update_item(
                Key={"run_id": str(run_id)},
                UpdateExpression="SET #status = :new_status",
                ConditionExpression=(
                    "#status = :awaiting AND requested_by = :sub AND plan_hash = :plan_hash"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":new_status": new_status,
                    ":awaiting": "AWAITING_APPROVAL",
                    ":sub": sub,
                    ":plan_hash": plan_hash,
                },
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ApprovalConflictError(
                    f"run {run_id} is not AWAITING_APPROVAL for requester {sub!r} "
                    f"with plan_hash {plan_hash!r}"
                ) from exc
            raise


class EventsTable:
    """Access to the append-only `events` table: append + query by run_id."""

    def __init__(
        self,
        table_name: str = DEFAULT_EVENTS_TABLE,
        resource: Any | None = None,
    ) -> None:
        self._resource = resource or boto3.resource("dynamodb")
        self._table = self._resource.Table(table_name)

    def append(self, event: Event) -> None:
        self._table.put_item(Item=_event_to_item(event))

    def query_by_run_id(self, run_id: uuid.UUID | str) -> list[Event]:
        resp = self._table.query(
            KeyConditionExpression=conditions.Key("run_id").eq(
                str(run_id)
            ),
        )
        items = sorted(resp.get("Items", []), key=lambda i: i["seq"])
        return [_item_to_event(item) for item in items]


def create_tables(
    resource: Any,
    runs_table_name: str = DEFAULT_RUNS_TABLE,
    events_table_name: str = DEFAULT_EVENTS_TABLE,
) -> None:
    """Create the `runs` and `events` tables with a moto/local DynamoDB
    resource. Used by tests; the real tables are provisioned by Terraform
    (infrastructure/modules/persistence)."""

    resource.create_table(
        TableName=runs_table_name,
        KeySchema=[{"AttributeName": "run_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "run_id", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
            {"AttributeName": "requested_by", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": GSI_STATUS,
                "KeySchema": [{"AttributeName": "status", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5,
                },
            },
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
