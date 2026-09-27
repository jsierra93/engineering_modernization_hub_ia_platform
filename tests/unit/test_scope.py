"""CLAUDE.md invariant #4: resolve_scope can only tighten."""

from __future__ import annotations

from core_py.scope import resolve_scope


def test_requester_exclusion_removes_a_path_the_strategy_allowed():
    scope = resolve_scope(["**/*.py"], requester_excluded_paths=["src/legacy/**"])

    assert scope.allows("src/models.py")
    assert not scope.allows("src/legacy/old.py")


def test_strategy_exclusion_applies_without_any_requester_input():
    scope = resolve_scope(["**/*.py"], ["**/ci/**"])

    assert not scope.allows("ci/deploy.py")


def test_requester_cannot_widen_what_the_strategy_never_allowed():
    scope = resolve_scope(["**/*.py"], requester_excluded_paths=[])

    assert not scope.allows("infra/main.tf")


def test_requester_cannot_reopen_a_strategy_exclusion():
    """Exclusions are unioned, never subtracted from each other -- an empty
    requester list must not cancel the strategy's own exclusions."""
    scope = resolve_scope(["**/*.py"], ["**/ci/**"], [])

    assert not scope.allows("ci/deploy.py")


def test_both_sides_exclusions_are_kept():
    scope = resolve_scope(["**/*.py"], ["**/ci/**"], ["src/legacy/**"])

    assert scope.excluded_paths == ["**/ci/**", "src/legacy/**"]
    assert scope.allows("src/models.py")
