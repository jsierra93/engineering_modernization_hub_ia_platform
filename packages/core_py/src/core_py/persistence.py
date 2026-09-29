"""DynamoDB access for the runs and events tables.
Deterministic zone: never imports Bedrock and never computes a verdict.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import boto3
import boto3.dynamodb.conditions as conditions
from botocore.exceptions import ClientError
from pydantic import BaseModel

from core_py.models import Event, Run


class ApprovalConflictError(Exception):
    pass


def _floats_to_decimal(item: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(item), parse_float=Decimal)

DEFAULT_RUNS_TABLE = os.environ.get("RUNS_TABLE_NAME", "modhub-runs")
DEFAULT_EVENTS_TABLE = os.environ.get("EVENTS_TABLE_NAME", "modhub-events")

MAX_APPEND_ATTEMPTS = 10

GSI_REQUESTED_BY = "gsi_requested_by"


def _run_to_item(run: Run) -> dict[str, Any]:
    item = run.model_dump(mode="json")
    item["run_id"] = str(run.run_id)
    return _floats_to_decimal(item)


# Rows outlive schema versions: unknown attributes are dropped instead of failing the read.
def _known_fields_only(model: type[BaseModel], item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key in model.model_fields}


def _item_to_run(item: dict[str, Any]) -> Run:
    return Run.model_validate(_known_fields_only(Run, item))


def _query_all(table: Any, **kwargs: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            return items
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def _event_to_item(event: Event) -> dict[str, Any]:
    item = event.model_dump(mode="json")
    item["run_id"] = str(event.run_id)
    return _floats_to_decimal(item)


def _item_to_event(item: dict[str, Any]) -> Event:
    return Event.model_validate(_known_fields_only(Event, item))


class RunsTable:
    def __init__(
        self,
        table_name: str = DEFAULT_RUNS_TABLE,
        resource: Any | None = None,
    ) -> None:
        self._resource = resource or boto3.resource("dynamodb")
        self._table = self._resource.Table(table_name)

    def put(self, run: Run) -> None:
        self._table.put_item(Item=_run_to_item(run))

    def update_fields(self, run: Run, *fields: str) -> None:
        item = _run_to_item(run)
        values = {name: item[name] for name in fields}
        values["updated_at"] = datetime.now(UTC).isoformat()
        names = {f"#f{i}": name for i, name in enumerate(values)}
        placeholders = {f":v{i}": value for i, value in enumerate(values.values())}
        self._table.update_item(
            Key={"run_id": item["run_id"]},
            UpdateExpression="SET " + ", ".join(f"#f{i} = :v{i}" for i in range(len(values))),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=placeholders,
        )

    def get(self, run_id: uuid.UUID | str) -> Run | None:
        resp = self._table.get_item(Key={"run_id": str(run_id)})
        item = resp.get("Item")
        return _item_to_run(item) if item else None

    def query_by_requested_by(self, requested_by: str) -> list[Run]:
        items = _query_all(
            self._table,
            IndexName=GSI_REQUESTED_BY,
            KeyConditionExpression=conditions.Key("requested_by").eq(requested_by),
        )
        return [_item_to_run(item) for item in items]

    def add_spend(self, run_id: uuid.UUID | str, delta: float) -> float:
        # Unconditional on purpose: the money is already spent, so the ledger must record it (invariant 6).
        resp = self._table.update_item(
            Key={"run_id": str(run_id)},
            UpdateExpression="SET spent_usd = spent_usd + :delta",
            ExpressionAttributeValues={":delta": Decimal(str(delta))},
            ReturnValues="UPDATED_NEW",
        )
        return float(resp["Attributes"]["spent_usd"])

    def record_pull_request(self, run_id: uuid.UUID | str, *, url: str, branch: str) -> str:
        try:
            self._table.update_item(
                Key={"run_id": str(run_id)},
                UpdateExpression="SET pull_request_url = :u, pull_request_branch = :b",
                ConditionExpression="attribute_not_exists(pull_request_url)",
                ExpressionAttributeValues={":u": url, ":b": branch},
            )
            return url
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            existing = self.get(run_id)
            return (existing.pull_request_url if existing else None) or url

    def approve_or_reject(
        self, run_id: uuid.UUID | str, *, sub: str, plan_hash: str, new_status: str
    ) -> None:
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
    def __init__(
        self,
        table_name: str = DEFAULT_EVENTS_TABLE,
        resource: Any | None = None,
    ) -> None:
        self._resource = resource or boto3.resource("dynamodb")
        self._table = self._resource.Table(table_name)

    def append(self, event: Event) -> None:
        self._table.put_item(Item=_event_to_item(event), ConditionExpression="attribute_not_exists(seq)")

    def append_next(self, event: Event) -> Event:
        seq = len(self.query_by_run_id(event.run_id))
        for _ in range(MAX_APPEND_ATTEMPTS):
            candidate = event.model_copy(update={"seq": seq})
            try:
                self.append(candidate)
                return candidate
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    raise
                seq += 1
        raise RuntimeError(f"could not append an event for run {event.run_id} after {MAX_APPEND_ATTEMPTS} attempts")

    def query_by_run_id(self, run_id: uuid.UUID | str) -> list[Event]:
        items = _query_all(self._table, KeyConditionExpression=conditions.Key("run_id").eq(str(run_id)))
        return [_item_to_event(item) for item in sorted(items, key=lambda i: i["seq"])]
