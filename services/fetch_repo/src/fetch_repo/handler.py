"""Downloads the tarball at repo@commit, sanitizes it, writes v0 to S3 plus one consolidated archive.
Returns presigned URLs so the credential-less sandbox can fetch the workspace and push its JUnit.
"""

from __future__ import annotations

import io
import tarfile
from dataclasses import dataclass
from typing import Any, Protocol

from fetch_repo.sanitize import TarSanitizationError, iter_sanitized_members

DEFAULT_WORKSPACE_BUCKET_ENV = "MODHUB_WORKSPACE_BUCKET"

PRESIGNED_URL_TTL_SECONDS = 1800


class HttpGetError(Exception):
    pass


class SupportsGet(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class FetchResult:
    run_id: str
    bucket: str
    prefix: str
    object_keys: list[str]
    workspace_get_url: str
    junit_put_url: str
    junit_key: str


def _tarball_url(repo: str, commit: str) -> str:
    return f"https://codeload.github.com/{repo}/tar.gz/{commit}"


def build_consolidated_archive(members: list) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for member in members:
            info = tarfile.TarInfo(name=member.path)
            info.size = len(member.data)
            archive.addfile(info, io.BytesIO(member.data))
    return buffer.getvalue()


def fetch_and_store_repo(
    run_id: str,
    repo: str,
    commit: str,
    bucket: str,
    http_session: SupportsGet,
    s3_resource: Any,
    *,
    version: str = "v0",
) -> FetchResult:
    url = _tarball_url(repo, commit)
    try:
        response = http_session.get(url, timeout=30)
        response.raise_for_status()
    except TarSanitizationError:
        raise
    except Exception as exc:  # noqa: BLE001 - re-raised as our own type
        raise HttpGetError(f"failed to download {url}: {exc}") from exc

    prefix = f"ws/{run_id}/{version}/"
    bucket_resource = s3_resource.Bucket(bucket)

    members = list(iter_sanitized_members(io.BytesIO(response.content)))

    object_keys: list[str] = []
    for member in members:
        key = f"{prefix}{member.path}"
        bucket_resource.put_object(Key=key, Body=member.data)
        object_keys.append(key)

    archive_key = f"ws/{run_id}/{version}.tar.gz"
    bucket_resource.put_object(Key=archive_key, Body=build_consolidated_archive(members))

    s3_client = s3_resource.meta.client
    workspace_get_url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": archive_key},
        ExpiresIn=PRESIGNED_URL_TTL_SECONDS,
    )
    junit_key = f"ws/{run_id}/junit/unit_tests.xml"
    junit_put_url = s3_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": junit_key},
        ExpiresIn=PRESIGNED_URL_TTL_SECONDS,
    )

    return FetchResult(
        run_id=run_id,
        bucket=bucket,
        prefix=prefix,
        object_keys=object_keys,
        workspace_get_url=workspace_get_url,
        junit_put_url=junit_put_url,
        junit_key=junit_key,
    )


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    import os

    import boto3
    import requests

    bucket = os.environ[DEFAULT_WORKSPACE_BUCKET_ENV]
    result = fetch_and_store_repo(
        run_id=event["run_id"],
        repo=event["repo"],
        commit=event["commit"],
        bucket=bucket,
        http_session=requests.Session(),
        s3_resource=boto3.resource("s3"),
    )
    return {
        "run_id": result.run_id,
        "bucket": result.bucket,
        "prefix": result.prefix,
        "object_count": len(result.object_keys),
        "workspace_get_url": result.workspace_get_url,
        "junit_put_url": result.junit_put_url,
        "junit_key": result.junit_key,
    }
