"""Task 3.1: load a dummy strategy manifest and validate it against the
SDK schema, including a failure case (max exceeds platform ceiling)."""

from __future__ import annotations

import pytest

from core_py.models import StrategyLimit, StrategyLimits, StrategyManifest
from strategies_sdk import (
    PLATFORM_CEILING,
    ManifestValidationError,
    PlatformCeiling,
    StrategyRegistry,
    validate_manifest,
)


def _dummy_manifest(**limit_overrides) -> StrategyManifest:
    limits = StrategyLimits(
        max_usd=StrategyLimit(default=1.0, max=2.0),
        max_iterations=StrategyLimit(default=1, max=2),
        max_minutes=StrategyLimit(default=10, max=20),
    )
    for field, limit in limit_overrides.items():
        setattr(limits, field, limit)

    return StrategyManifest(
        id="dummy-strategy",
        version="0.1.0",
        title="Dummy",
        inputs={"target_version": {"type": "string", "required": True}},
        limits=limits,
        checks=["install", "unit_tests"],
        writable_paths=["**/*.py"],
        sources=["https://example.com/docs"],
    )


class _DummyModule:
    def manifest(self) -> StrategyManifest:
        return _dummy_manifest()


def test_valid_dummy_manifest_passes_validation():
    manifest = _dummy_manifest()
    validate_manifest(manifest)  # must not raise


def test_registry_loads_and_validates_dummy_manifest():
    registry = StrategyRegistry()
    manifest = registry.register(_DummyModule())

    assert manifest.id == "dummy-strategy"
    assert registry.get("dummy-strategy") is manifest
    assert manifest in registry.list()


def test_platform_ceiling_matches_claude_md():
    assert PLATFORM_CEILING == PlatformCeiling(max_usd=10, max_iterations=5, max_minutes=60)


def test_manifest_exceeding_platform_ceiling_fails_validation():
    manifest = _dummy_manifest(
        max_usd=StrategyLimit(default=1.0, max=999.0),
    )

    with pytest.raises(ManifestValidationError, match="platform ceiling"):
        validate_manifest(manifest)


def test_manifest_default_exceeding_own_max_fails_validation():
    manifest = _dummy_manifest(
        max_iterations=StrategyLimit(default=10, max=2),
    )

    with pytest.raises(ManifestValidationError, match="exceeds limits"):
        validate_manifest(manifest)


def test_manifest_without_checks_fails_validation():
    manifest = _dummy_manifest()
    manifest.checks = []

    with pytest.raises(ManifestValidationError, match="checks"):
        validate_manifest(manifest)
