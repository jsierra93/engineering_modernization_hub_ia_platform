"""The agent's view of its own run's files.

Unlike the sandbox (zero AWS credentials, presigned URLs only -- CLAUDE.md
invariant #8), `agent_phase` runs as a Lambda with real, scoped IAM: it can
read/write S3 directly, but only under its own run's prefix
(`ws/<run_id>/`) -- the permissions table's own line for this component:
"workspace de su run vía policy gate". `S3Workspace` enforces that scoping
in code (prefix-joins every path), and the Terraform-side IAM policy
enforces it again independently -- the same defense-in-depth pattern as
`fetch_repo`'s tar-slip check running even though the tarball already came
from a sanitized source.

`Workspace` is a Protocol so tests use a plain in-memory dict instead of
moto -- workspace correctness here is about "does path-scoping work",
which doesn't need a real S3 backend to verify.
"""

from __future__ import annotations

from core_py.scope import normalize

from typing import Any, Protocol


def _is_within_root(candidate: str) -> bool:
    return normalize(candidate) is not None

class WorkspacePathError(Exception):
    """A tool asked for a path that escapes its own run's workspace."""


class Workspace(Protocol):
    def read(self, path: str) -> str: ...
    def write(self, path: str, content: str) -> None: ...
    def list(self, prefix: str = "") -> list[str]: ...


class S3Workspace:
    """Real workspace, scoped to `ws/<run_id>/<version>/` in one bucket.

    `s3_resource` is injected (moto-mocked in integration tests); the
    prefix scoping below is what actually matters for unit tests, and
    that's exercised without any S3 backend via `_join`.
    """

    def __init__(self, s3_resource: Any, bucket: str, run_id: str, version: str = "v0") -> None:
        self._bucket = s3_resource.Bucket(bucket)
        self._prefix = f"ws/{run_id}/{version}/"

    def _join(self, path: str) -> str:
        if not _is_within_root(path):
            raise WorkspacePathError(f"path {path!r} escapes the workspace root")
        return f"{self._prefix}{path}"

    def read(self, path: str) -> str:
        key = self._join(path)
        obj = self._bucket.Object(key).get()
        return obj["Body"].read().decode("utf-8", errors="replace")

    def write(self, path: str, content: str) -> None:
        key = self._join(path)
        self._bucket.put_object(Key=key, Body=content.encode("utf-8"))

    def list(self, prefix: str = "") -> list[str]:
        full_prefix = self._join(prefix) if prefix else self._prefix
        return [
            obj.key[len(self._prefix) :]
            for obj in self._bucket.objects.filter(Prefix=full_prefix)
        ]
