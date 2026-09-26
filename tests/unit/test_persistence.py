"""Task 1.4: moto-backed pytest for the runs/events DynamoDB access layer."""

from __future__ import annotations

import uuid

import boto3
import pytest
from moto import mock_aws

from core_py.models import Event, Run
from core_py.persistence import BudgetExceededError, EventsTable, RunsTable, create_tables


@pytest.fixture()
def dynamodb_resource():
    with mock_aws():
        yield boto3.resource("dynamodb", region_name="us-east-1")


@pytest.fixture()
def tables(dynamodb_resource):
    create_tables(dynamodb_resource)
    return RunsTable(resource=dynamodb_resource), EventsTable(resource=dynamodb_resource)


def _make_run(**overrides) -> Run:
    defaults = dict(
        repo="https://github.com/example/demo",
        commit="a" * 40,
        objetivo="Migrate to Pydantic v2",
        requested_by="user-123",
        strategy_id="python-pydantic-v2",
        strategy_version="1.0.0",
        max_usd=5.0,
        max_iterations=3,
        max_minutes=20,
    )
    defaults.update(overrides)
    return Run(**defaults)


def test_put_and_get_run(tables):
    runs_table, _ = tables
    run = _make_run()

    runs_table.put(run)
    fetched = runs_table.get(run.run_id)

    assert fetched is not None
    assert fetched.run_id == run.run_id
    assert fetched.repo == run.repo
    assert fetched.status == run.status


def test_get_missing_run_returns_none(tables):
    runs_table, _ = tables
    assert runs_table.get(uuid.uuid4()) is None


def test_query_by_status(tables):
    runs_table, _ = tables
    run_a = _make_run(requested_by="user-a")
    run_b = _make_run(requested_by="user-b")
    runs_table.put(run_a)
    runs_table.put(run_b)

    results = runs_table.query_by_status(run_a.status.value)
    result_ids = {r.run_id for r in results}

    assert run_a.run_id in result_ids
    assert run_b.run_id in result_ids


def test_query_by_requested_by(tables):
    runs_table, _ = tables
    mine = _make_run(requested_by="jorgesierra93@gmail.com")
    other = _make_run(requested_by="someone-else")
    runs_table.put(mine)
    runs_table.put(other)

    results = runs_table.query_by_requested_by("jorgesierra93@gmail.com")

    assert {r.run_id for r in results} == {mine.run_id}


def test_events_append_and_query_by_run_id(tables):
    _, events_table = tables
    run_id = uuid.uuid4()

    events_table.append(Event(run_id=run_id, seq=0, type="RunCreated"))
    events_table.append(Event(run_id=run_id, seq=1, type="PhaseStarted"))
    events_table.append(Event(run_id=uuid.uuid4(), seq=0, type="RunCreated"))

    results = events_table.query_by_run_id(run_id)

    assert [e.seq for e in results] == [0, 1]
    assert [e.type for e in results] == ["RunCreated", "PhaseStarted"]


def test_add_spend_accumulates_within_budget(tables):
    runs_table, _ = tables
    run = _make_run(max_usd=5.0)
    runs_table.put(run)

    runs_table.add_spend(run.run_id, 2.0, max_usd=5.0)
    runs_table.add_spend(run.run_id, 2.0, max_usd=5.0)

    fetched = runs_table.get(run.run_id)
    assert fetched.spent_usd == pytest.approx(4.0)


def test_add_spend_second_call_that_would_exceed_max_usd_raises(tables):
    """Task 2.6: two sequential adds that together would exceed max_usd --
    the second must fail (a specific, catchable exception) rather than
    silently over-committing."""
    runs_table, _ = tables
    run = _make_run(max_usd=5.0)
    runs_table.put(run)

    runs_table.add_spend(run.run_id, 4.0, max_usd=5.0)

    with pytest.raises(BudgetExceededError):
        runs_table.add_spend(run.run_id, 2.0, max_usd=5.0)

    # The rejected call must not have partially applied.
    fetched = runs_table.get(run.run_id)
    assert fetched.spent_usd == pytest.approx(4.0)
