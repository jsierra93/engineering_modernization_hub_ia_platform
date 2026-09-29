"""Downloads the tarball at repo@commit, sanitizes it, writes v0 to S3 plus one consolidated archive.
Returns presigned URLs so the credential-less sandbox can fetch the workspace and push its JUnit.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Protocol

from core_py.constants import BASELINE_VERSION
from core_py.constants import WORKSPACE_BUCKET_ENV as DEFAULT_WORKSPACE_BUCKET_ENV

from core_py.workspace import build_archive, presign_sandbox_io, store_archive, version_prefix

from fetch_repo.sanitize import iter_sanitized_members

BASELINE_JUNIT_FILENAME = "unit_tests.xml"



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


def fetch_and_store_repo(
    run_id: str,
    repo: str,
    commit: str,
    bucket: str,
    http_session: SupportsGet,
    s3_resource: Any,
    *,
    version: str = BASELINE_VERSION,
) -> FetchResult:
    url = _tarball_url(repo, commit)
    try:
        response = http_session.get(url, timeout=30)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - re-raised as our own type
        raise HttpGetError(f"failed to download {url}: {exc}") from exc

    prefix = version_prefix(run_id, version)
    bucket_resource = s3_resource.Bucket(bucket)

    members = list(iter_sanitized_members(io.BytesIO(response.content)))

    object_keys: list[str] = []
    for member in members:
        key = f"{prefix}{member.path}"
        bucket_resource.put_object(Key=key, Body=member.data)
        object_keys.append(key)

    store_archive(s3_resource, bucket, run_id, version, build_archive((member.path, member.data) for member in members))
    handoff = presign_sandbox_io(s3_resource, bucket, run_id, version, BASELINE_JUNIT_FILENAME)

    return FetchResult(
        run_id=run_id,
        bucket=bucket,
        prefix=prefix,
        object_keys=object_keys,
        workspace_get_url=handoff["workspace_get_url"],
        junit_put_url=handoff["junit_put_url"],
        junit_key=handoff["junit_key"],
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
