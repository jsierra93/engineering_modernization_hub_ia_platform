"""Task 3.2: the registry can load and validate the python-pydantic-v2
strategy manifest, and its shape matches the spec in PLAN.md."""

from __future__ import annotations

from python_pydantic_v2 import manifest as pydantic_v2_manifest
from strategies_sdk import StrategyRegistry


class _PydanticV2Module:
    def manifest(self):
        return pydantic_v2_manifest()


def test_registry_loads_and_validates_python_pydantic_v2():
    registry = StrategyRegistry()
    manifest = registry.register(_PydanticV2Module())

    assert manifest.id == "python-pydantic-v2"
    assert manifest.version == "1.0.0"
    assert manifest.title == "Pydantic v1 -> v2"


def test_manifest_inputs_shape():
    manifest = pydantic_v2_manifest()

    assert manifest.inputs["target_version"]["enum"] == ["2.9", "2.10", "2.11"]
    assert manifest.inputs["target_version"]["required"] is True
    assert manifest.inputs["python_version"]["enum"] == ["3.10", "3.11", "3.12"]
    assert manifest.inputs["python_version"]["required"] is False


def test_manifest_limits():
    manifest = pydantic_v2_manifest()

    assert manifest.limits.max_iterations.default == 3
    assert manifest.limits.max_iterations.max == 5
    assert manifest.limits.max_usd.default == 2.0
    assert manifest.limits.max_usd.max == 5.0
    assert manifest.limits.max_minutes.default == 20
    assert manifest.limits.max_minutes.max == 45


def test_manifest_checks_writable_paths_and_sources():
    manifest = pydantic_v2_manifest()

    assert manifest.checks == ["install", "unit_tests", "lint"]
    assert "**/*.py" in manifest.writable_paths
    assert "pyproject.toml" in manifest.writable_paths
    assert "requirements*.txt" in manifest.writable_paths
    assert "https://docs.pydantic.dev/latest/migration/" in manifest.sources
