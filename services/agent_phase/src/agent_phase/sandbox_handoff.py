"""Snapshots workspace versions in S3 and repackages the workspace as a tar.gz with fresh presigned URLs for the sandbox."""

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


def copy_version(s3_resource: Any, bucket: str, run_id: str, src: str, dst: str) -> int:
    bucket_resource = s3_resource.Bucket(bucket)
    src_prefix = f"ws/{run_id}/{src}/"
    dst_prefix = f"ws/{run_id}/{dst}/"

    copied = 0
    for obj in bucket_resource.objects.filter(Prefix=src_prefix):
        rel_path = obj.key[len(src_prefix) :]
        if not rel_path:
            continue
        bucket_resource.copy({"Bucket": bucket, "Key": obj.key}, f"{dst_prefix}{rel_path}")
        copied += 1
    return copied
