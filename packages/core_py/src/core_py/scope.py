"""Writable-path resolution (invariant 4): normalizes paths and only ever tightens scope."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from fnmatch import fnmatchcase


# Normalize before matching, or `src/../ci/x.py` walks around an exclusion of `ci/`.
def normalize(path: str) -> str | None:
    if not path:
        return None
    candidate = path.replace("\\", "/")
    if candidate.startswith("/") or (len(candidate) > 1 and candidate[1] == ":"):
        return None
    normalized = posixpath.normpath(candidate)
    if normalized == "." or normalized.startswith("../"):
        return None
    return normalized


def matches(path: str, pattern: str) -> bool:
    normalized = normalize(path)
    if normalized is None:
        return False
    if fnmatchcase(normalized, pattern):
        return True
    return pattern.startswith("**/") and fnmatchcase(normalized, pattern[3:])


@dataclass(frozen=True)
class ResolvedScope:
    writable_paths: list[str]
    excluded_paths: list[str]

    def allows(self, path: str) -> bool:
        if normalize(path) is None:
            return False
        if any(matches(path, pattern) for pattern in self.excluded_paths):
            return False
        return any(matches(path, pattern) for pattern in self.writable_paths)


def resolve_scope(
    strategy_writable_paths: list[str],
    strategy_excluded_paths: list[str] | None = None,
    requester_excluded_paths: list[str] | None = None,
) -> ResolvedScope:
    return ResolvedScope(
        writable_paths=list(strategy_writable_paths),
        excluded_paths=[*(strategy_excluded_paths or []), *(requester_excluded_paths or [])],
    )
