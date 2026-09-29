"""Unified diff between the baseline (v0) and working (v1) workspaces, computed from S3."""

from __future__ import annotations

import difflib
from typing import Any

from core_py.constants import BASELINE_VERSION, WORKING_VERSION
from core_py.workspace import read_version

MAX_DIFF_CHARS = 200_000


def _read_text_version(s3_resource: Any, bucket: str, run_id: str, version: str) -> dict[str, str]:
    files: dict[str, str] = {}
    for path, body in read_version(s3_resource, bucket, run_id, version).items():
        try:
            files[path] = body.decode("utf-8")
        except UnicodeDecodeError:
            files[path] = "<binary>"
    return files


def compute_diff(
    s3_resource: Any,
    bucket: str,
    run_id: str,
    baseline_version: str = BASELINE_VERSION,
    working_version: str = WORKING_VERSION,
) -> tuple[str, list[str]]:
    before = _read_text_version(s3_resource, bucket, run_id, baseline_version)
    after = _read_text_version(s3_resource, bucket, run_id, working_version)
    if not after:
        return "", []

    chunks: list[str] = []
    changed: list[str] = []

    for path in sorted(set(before) | set(after)):
        old = before.get(path, "")
        new = after.get(path, "")
        if old == new:
            continue
        changed.append(path)
        chunks.extend(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )

    diff = "".join(chunks)
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n[truncated]\n"
    return diff, changed
