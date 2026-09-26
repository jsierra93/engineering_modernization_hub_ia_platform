"""Lambda handler for `fetch_repo` (PLAN.md task 2.2).

Downloads the exact tarball for `(repo, commit)` from GitHub's codeload
service, sanitizes it (see `fetch_repo.sanitize`), and writes each
accepted file to S3 under `ws/<run_id>/v0/<path>`.

Both the HTTP client and the S3 resource are injected so this is fully
testable without network or real AWS: an HTTP session (anything exposing
`.get(url, ...) -> response` with `.content`/`.raise_for_status()`, e.g.
`requests.Session` or a `responses`-mocked one) and a boto3 S3 resource
(moto-mocked in tests), matching the injection pattern already used by
`core_py.persistence.RunsTable` and `services/api/src/api/handler.py`.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Protocol

from fetch_repo.sanitize import TarSanitizationError, iter_sanitized_members

DEFAULT_WORKSPACE_BUCKET_ENV = "MODHUB_WORKSPACE_BUCKET"


class HttpGetError(Exception):
    """Raised when the tarball download itself fails (network error, non-2xx
    status). Kept distinct from `TarSanitizationError` so callers can tell
    "couldn't fetch it" apart from "fetched something unsafe"."""


class SupportsGet(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class FetchResult:
    run_id: str
    bucket: str
    prefix: str
    object_keys: list[str]


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
    version: str = "v0",
) -> FetchResult:
    """Fetch `repo`@`commit`'s tarball, sanitize it, and write every
    accepted entry to `s3://bucket/ws/<run_id>/<version>/<path>`.

    Raises `HttpGetError` if the download fails, or
    `TarSanitizationError` if the tarball contains anything unsafe (path
    traversal, symlinks, oversized content, ...). In either case nothing
    partially written to S3 for this run should be trusted -- the caller
    (the state machine's `fetch_repo` phase) is expected to fail the run
    rather than proceed with a partial workspace.
    """

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

    object_keys: list[str] = []
    for member in iter_sanitized_members(io.BytesIO(response.content)):
        key = f"{prefix}{member.path}"
        bucket_resource.put_object(Key=key, Body=member.data)
        object_keys.append(key)

    return FetchResult(run_id=run_id, bucket=bucket, prefix=prefix, object_keys=object_keys)


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Step Functions task entrypoint.

    Expected input: `{"run_id": ..., "repo": ..., "commit": ...}`. The
    real HTTP session and S3 resource are constructed here; tests call
    `fetch_and_store_repo` directly with injected fakes.
    """
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
    }
