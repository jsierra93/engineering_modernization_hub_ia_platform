"""Repackages the current (agent-modified) workspace for the sandbox,
after Implement or a Fix iteration writes files.

MVP simplification, documented rather than hidden: this prototype mutates
a single `ws/<run_id>/v0/` prefix in place (the one fetch_repo populated)
instead of writing a fresh `ws/v1`, `ws/v2`, ... per iteration as the
design artifact's fuller version describes ("Cada iteración queda como
ws/vN en S3"). Functionally the pipeline is identical -- fetch, plan,
implement, verify, fix, re-verify -- but the per-iteration audit trail
granularity is reduced to "the latest state" rather than a full history of
intermediate versions. Revisiting this to write real vN snapshots is a
natural follow-up once the MVP path is proven end-to-end, not a silent
regression: it's called out here and in the top-level summary.

Same reasoning as fetch_repo's own consolidated-archive step: a presigned
URL names exactly one S3 object, and the workspace is many files, so
repackaging into one tar.gz is what makes a single presigned GET possible
for the sandbox (which still has zero AWS credentials -- CLAUDE.md
invariant #8, unchanged by any of this).
"""

from __future__ import annotations

import io
import tarfile
from typing import Any

PRESIGNED_URL_TTL_SECONDS = 1800


def repackage_workspace_for_sandbox(
    s3_resource: Any,
    bucket: str,
    run_id: str,
    *,
    junit_filename: str,
    version: str = "v0",
) -> dict[str, str]:
    """Archives everything currently under `ws/<run_id>/<version>/`,
    uploads it as one object, and returns fresh presigned GET (workspace)
    and PUT (JUnit) URLs -- the same two fields fetch_repo's handler
    returns, so the ASL's Verify state consumes them identically to how
    Baseline already does."""

    bucket_resource = s3_resource.Bucket(bucket)
    prefix = f"ws/{run_id}/{version}/"

    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:gz") as archive:
        for obj in bucket_resource.objects.filter(Prefix=prefix):
            rel_path = obj.key[len(prefix) :]
            if not rel_path:
                continue
            data = obj.get()["Body"].read()
            info = tarfile.TarInfo(name=rel_path)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))

    archive_key = f"ws/{run_id}/{version}.tar.gz"
    bucket_resource.put_object(Key=archive_key, Body=archive_buffer.getvalue())

    client = s3_resource.meta.client
    workspace_get_url = client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": archive_key}, ExpiresIn=PRESIGNED_URL_TTL_SECONDS
    )
    junit_key = f"ws/{run_id}/junit/{junit_filename}"
    junit_put_url = client.generate_presigned_url(
        "put_object", Params={"Bucket": bucket, "Key": junit_key}, ExpiresIn=PRESIGNED_URL_TTL_SECONDS
    )

    return {
        "workspace_get_url": workspace_get_url,
        "junit_put_url": junit_put_url,
        "junit_key": junit_key,
        "bucket": bucket,
    }
