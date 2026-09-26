"""Proves the real ASL usage path: compute_verdict reading JUnit from S3
by key (core_ops's actual IAM scope is s3:GetObject on ws/*/junit/*) --
not just the inline-XML shortcut the other handler tests use."""

from __future__ import annotations

import boto3
import pytest
from core_py.models import Restricciones, Run
from core_py.persistence import RunsTable, create_tables
from moto import mock_aws

from core_ops.handler import _run

RUN_ID = "44444444-4444-4444-4444-444444444444"
BUCKET = "modhub-workspaces"
PASSING_JUNIT = '<testsuites><testsuite tests="2"><testcase name="a"/><testcase name="b"/></testsuite></testsuites>'


@pytest.fixture()
def env():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        create_tables(dynamodb)
        runs_table = RunsTable(resource=dynamodb)
        runs_table.put(
            Run(
                run_id=RUN_ID,
                repo="octocat/Hello-World",
                commit="a" * 40,
                objetivo="x",
                restricciones=Restricciones(),
                requested_by="user-1",
                strategy_id="python-pydantic-v2",
                strategy_version="1.0.0",
                max_usd=2.0,
                max_iterations=3,
                max_minutes=20,
            )
        )

        s3 = boto3.resource("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        s3.Bucket(BUCKET).put_object(Key=f"ws/{RUN_ID}/junit/baseline.xml", Body=PASSING_JUNIT.encode())
        s3.Bucket(BUCKET).put_object(Key=f"ws/{RUN_ID}/junit/verify_iter1.xml", Body=PASSING_JUNIT.encode())

        yield runs_table, s3


def test_compute_verdict_reads_junit_from_s3_by_key(env):
    runs_table, s3 = env

    result = _run(
        {
            "action": "compute_verdict",
            "run_id": RUN_ID,
            "workspaces_bucket": BUCKET,
            "baseline_junit_key": f"ws/{RUN_ID}/junit/baseline.xml",
            "final_junit_key": f"ws/{RUN_ID}/junit/verify_iter1.xml",
            "checks": {"install": True, "unit_tests": True},
        },
        runs_table=runs_table,
        s3_resource=s3,
    )

    assert result["status"] == "LISTO_PARA_REVISION"
