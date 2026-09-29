"""Owner of the ws/<run_id>/... layout in S3: keys, version copies, archives and the presigned URLs the sandbox uses.
Nothing else spells a workspace key, so the layout can change in one place.
"""

from __future__ import annotations

import io
import tarfile
from collections.abc import Iterable
from typing import Any

from core_py.constants import PRESIGNED_URL_TTL_SECONDS


def version_prefix(run_id: str, version: str) -> str:
    return f"ws/{run_id}/{version}/"


def archive_key(run_id: str, version: str) -> str:
    return f"ws/{run_id}/{version}.tar.gz"


def junit_key(run_id: str, filename: str) -> str:
    return f"ws/{run_id}/junit/{filename}"


def phase_trail_key(run_id: str, name: str) -> str:
    return f"ws/{run_id}/phases/{name}.json"


def diff_key(run_id: str) -> str:
    return f"ws/{run_id}/diff.patch"


def build_archive(files: Iterable[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path, data in files:
            info = tarfile.TarInfo(name=path)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def read_version(s3_resource: Any, bucket: str, run_id: str, version: str) -> dict[str, bytes]:
    prefix = version_prefix(run_id, version)
    files: dict[str, bytes] = {}
    for obj in s3_resource.Bucket(bucket).objects.filter(Prefix=prefix):
        rel_path = obj.key[len(prefix) :]
        if not rel_path or rel_path.endswith("/"):
            continue
        files[rel_path] = obj.get()["Body"].read()
    return files


def read_files(s3_resource: Any, bucket: str, run_id: str, version: str, paths: list[str]) -> dict[str, bytes]:
    prefix = version_prefix(run_id, version)
    return {path: s3_resource.Object(bucket, f"{prefix}{path}").get()["Body"].read() for path in paths}


def copy_version(s3_resource: Any, bucket: str, run_id: str, src: str, dst: str) -> int:
    bucket_resource = s3_resource.Bucket(bucket)
    src_prefix = version_prefix(run_id, src)
    dst_prefix = version_prefix(run_id, dst)

    copied = 0
    for obj in bucket_resource.objects.filter(Prefix=src_prefix):
        rel_path = obj.key[len(src_prefix) :]
        if not rel_path:
            continue
        bucket_resource.copy({"Bucket": bucket, "Key": obj.key}, f"{dst_prefix}{rel_path}")
        copied += 1
    return copied


def store_archive(s3_resource: Any, bucket: str, run_id: str, version: str, archive: bytes) -> str:
    key = archive_key(run_id, version)
    s3_resource.Bucket(bucket).put_object(Key=key, Body=archive)
    return key


def presign_sandbox_io(
    s3_resource: Any, bucket: str, run_id: str, version: str, junit_filename: str
) -> dict[str, str]:
    client = s3_resource.meta.client
    workspace_get_url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": archive_key(run_id, version)},
        ExpiresIn=PRESIGNED_URL_TTL_SECONDS,
    )
    key = junit_key(run_id, junit_filename)
    junit_put_url = client.generate_presigned_url(
        "put_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=PRESIGNED_URL_TTL_SECONDS
    )
    return {"workspace_get_url": workspace_get_url, "junit_put_url": junit_put_url, "junit_key": key, "bucket": bucket}


def prepare_sandbox_io(
    s3_resource: Any, bucket: str, run_id: str, version: str, junit_filename: str
) -> dict[str, str]:
    files = read_version(s3_resource, bucket, run_id, version)
    store_archive(s3_resource, bucket, run_id, version, build_archive(files.items()))
    return presign_sandbox_io(s3_resource, bucket, run_id, version, junit_filename)
