"""CLAUDE.md invariant #4: resolve_scope intersects what the strategy
declared writable with the requester's exclusions -- it can only tighten.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch


def matches(path: str, pattern: str) -> bool:
    """fnmatch has no notion of `**`, so a leading `**/` would fail to match
    anything at the workspace root: `**/ci/**` would miss `ci/deploy.py`,
    and `**/*.py` would miss `setup.py`. Both are meant to match."""

    if fnmatch(path, pattern):
        return True
    return pattern.startswith("**/") and fnmatch(path, pattern[3:])


@dataclass(frozen=True)
class ResolvedScope:
    writable_paths: list[str]
    excluded_paths: list[str]

    def allows(self, path: str) -> bool:
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
