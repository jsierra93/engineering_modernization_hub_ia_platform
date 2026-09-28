"""CLAUDE.md invariant #4: resolve_scope intersects what the strategy
declared writable with the requester's exclusions -- it can only tighten.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from fnmatch import fnmatchcase


def normalize(path: str) -> str | None:
    """The workspace-relative form of `path`, or None if it is not a path
    inside the workspace at all.

    Matching a raw string is not enough: `src/../ci/x.py` names the same
    file as `ci/x.py` but does not match the pattern that excludes it, so
    every exclusion could be walked around by spelling the path
    differently. Normalizing first is what makes the exclusion mean the
    file rather than the spelling."""

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
    """fnmatch has no notion of `**`, so a leading `**/` would fail to match
    anything at the workspace root: `**/ci/**` would miss `ci/deploy.py`,
    and `**/*.py` would miss `setup.py`. Both are meant to match."""

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
        # A path that does not normalize is not "outside every pattern", it
        # is not a workspace path -- deny rather than fall through.
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
    """Exclusions from both sides are unioned, never subtracted from each
    other: neither the strategy nor the requester can re-open what the
    other closed."""

    return ResolvedScope(
        writable_paths=list(strategy_writable_paths),
        excluded_paths=[*(strategy_excluded_paths or []), *(requester_excluded_paths or [])],
    )
