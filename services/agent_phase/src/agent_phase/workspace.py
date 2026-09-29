"""The agent's view of its own run's files in S3, scoped to ws/<run_id>/<version>/."""

from __future__ import annotations

from core_py.constants import BASELINE_VERSION
from core_py.scope import normalize
from core_py.workspace import version_prefix

from typing import Any, Protocol


def _is_within_root(candidate: str) -> bool:
    return normalize(candidate) is not None

class WorkspacePathError(Exception):
    pass


class Workspace(Protocol):
    def read(self, path: str) -> str: ...
    def write(self, path: str, content: str) -> None: ...
    def list(self, prefix: str = "") -> list[str]: ...


class S3Workspace:
    def __init__(self, s3_resource: Any, bucket: str, run_id: str, version: str = BASELINE_VERSION) -> None:
        self._bucket = s3_resource.Bucket(bucket)
        self._prefix = version_prefix(run_id, version)

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
