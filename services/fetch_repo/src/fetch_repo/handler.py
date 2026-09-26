"""Lambda handler for `fetch_repo` (PLAN.md task 2.2).

Downloads the exact tarball for `(repo, commit)` from GitHub's codeload
service, sanitizes it (see `fetch_repo.sanitize`), and writes each
accepted file to S3 under `ws/<run_id>/v0/<path>` -- plus a single
consolidated `ws/<run_id>/v0.tar.gz` archive of the same sanitized
content, and two presigned URLs (task 2.3's cross-agent gap closure, see
CLAUDE.md invariant #8 and `infrastructure/modules/orchestration/asl/
state_machine.asl.json`'s `Baseline` state comment):

  - `workspace_get_url`: a short-lived presigned GET for the consolidated
    archive, so the sandbox container -- which has zero AWS credentials
    or SDK by design -- can fetch its input with one plain HTTPS GET
    instead of many, and without ever touching an AWS API.
  - `junit_put_url`: a presigned PUT for `ws/<run_id>/junit/unit_tests.xml`,
    matching `core_ops`'s own IAM scope (`ws/*/junit/*`) exactly, so the
    sandbox can push its JUnit result the same way.

A per-object presigned URL is why the archive step exists at all -- a
presigned URL names exactly one S3 object, and the workspace is many
files, so a single consolidated archive is the only way to hand the
sandbox "the whole workspace" through one URL.

Both the HTTP client and the S3 resource are injected so this is fully
testable without network or real AWS: an HTTP session (anything exposing
`.get(url, ...) -> response` with `.content`/`.raise_for_status()`, e.g.
`requests.Session` or a `responses`-mocked one) and a boto3 S3 resource
(moto-mocked in tests), matching the injection pattern already used by
`core_py.persistence.RunsTable` and `services/api/src/api/handler.py`.
Presigning itself is a local signing operation (no network call), so it
works identically against a moto-mocked resource and a real one.
"""

from __future__ import annotations

import io
import tarfile
from dataclasses import dataclass
from typing import Any, Protocol

from fetch_repo.sanitize import TarSanitizationError, iter_sanitized_members

DEFAULT_WORKSPACE_BUCKET_ENV = "MODHUB_WORKSPACE_BUCKET"

# How long the sandbox has to actually use these URLs. Generous enough for
# a Fargate cold start + a baseline test run, short enough to bound the
# exposure of a leaked URL (CLAUDE.md invariant #8's whole point).
PRESIGNED_URL_TTL_SECONDS = 1800


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
    workspace_get_url: str
    junit_put_url: str
    junit_key: str


def _tarball_url(repo: str, commit: str) -> str:
    return f"https://codeload.github.com/{repo}/tar.gz/{commit}"


def build_consolidated_archive(members: list) -> bytes:
    """Pack already-sanitized members into one in-memory tar.gz.

    A presigned URL always names exactly one S3 object, and the workspace
    is many files -- this is the only way to hand the sandbox "the whole
    workspace" through a single presigned GET (see module docstring).
    Pure and S3-free on purpose: the interesting behavior here (does the
    archive actually contain what it should) is fully testable without
    moto or any mocking, so it gets its own function rather than being
    inline in `fetch_and_store_repo`.
    """
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
        "workspace_get_url": result.workspace_get_url,
        "junit_put_url": result.junit_put_url,
        "junit_key": result.junit_key,
    }
