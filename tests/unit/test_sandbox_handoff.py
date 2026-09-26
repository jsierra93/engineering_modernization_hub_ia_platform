"""Verifies the repackaged archive actually reflects what the agent wrote
(not a stale copy of the original fetch), and that both URLs are usable
presigned S3 URLs -- same verification style as
test_fetch_repo.py::test_consolidated_archive_and_presigned_urls (using
listing, not a follow-up get_object, per that file's own note on a
moto/pytest quirk that made a direct GET-after-PUT flaky in this repo)."""

from __future__ import annotations

import io
import tarfile

import boto3
from moto import mock_aws

from agent_phase.sandbox_handoff import repackage_workspace_for_sandbox

BUCKET = "modhub-workspaces"
RUN_ID = "33333333-3333-3333-3333-333333333333"


def test_repackage_reflects_current_workspace_contents():
    with mock_aws():
        resource = boto3.resource("s3", region_name="us-east-1")
        resource.create_bucket(Bucket=BUCKET)
        bucket = resource.Bucket(BUCKET)
        bucket.put_object(Key=f"ws/{RUN_ID}/v0/pyproject.toml", Body=b"[project]")
        bucket.put_object(Key=f"ws/{RUN_ID}/v0/src/models.py", Body=b"# fixed by the agent\n")

        result = repackage_workspace_for_sandbox(resource, BUCKET, RUN_ID, junit_filename="verify_iter1.xml")

        archive_key = f"ws/{RUN_ID}/v0.tar.gz"
        listed = {obj.key for obj in bucket.objects.all()}
        assert archive_key in listed

        archive_bytes = resource.meta.client.get_object(Bucket=BUCKET, Key=archive_key)["Body"].read()
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            contents = {m.name: archive.extractfile(m).read() for m in archive.getmembers()}

        assert contents["src/models.py"] == b"# fixed by the agent\n"
        assert contents["pyproject.toml"] == b"[project]"

        assert archive_key in result["workspace_get_url"]
        assert f"ws/{RUN_ID}/junit/verify_iter1.xml" == result["junit_key"]
        assert "Signature" in result["junit_put_url"]
