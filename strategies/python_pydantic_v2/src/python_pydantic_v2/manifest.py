"""Manifest for the python-pydantic-v2 strategy: inputs, limits, checks, writable and excluded paths."""

from __future__ import annotations

from core_py.models import CheckSpec, StrategyLimit, StrategyLimits, StrategyManifest

_INPUTS = {
    "target_version": {
        "type": "string",
        "required": True,
        "enum": ["2.9", "2.10", "2.11"],
        "description": "Target Pydantic v2 minor version to migrate to.",
    },
    "python_version": {
        "type": "string",
        "required": False,
        "enum": ["3.10", "3.11", "3.12"],
        "description": "Target Python version, if the migration should also bump it.",
    },
}

_LIMITS = StrategyLimits(
    max_iterations=StrategyLimit(default=3, max=5),
    max_usd=StrategyLimit(default=2.0, max=5.0),
    max_minutes=StrategyLimit(default=20, max=45),
)

_CHECKS = [CheckSpec(name="unit_tests"), CheckSpec(name="lint", blocking=False)]

_WRITABLE_PATHS = [
    "**/*.py",
    "pyproject.toml",
    "requirements*.txt",
]
_EXCLUDED_PATHS = [
    "**/ci/**",
    "**/*.tf",
    "**/conftest.py",
    "pytest.ini",
    "tox.ini",
    "setup.cfg",
]

_SOURCES = ["https://docs.pydantic.dev/latest/migration/"]


def manifest() -> StrategyManifest:
    return StrategyManifest(
        id="python-pydantic-v2",
        version="1.0.0",
        title="Pydantic v1 -> v2",
        inputs=_INPUTS,
        limits=_LIMITS,
        checks=_CHECKS,
        writable_paths=_WRITABLE_PATHS,
        excluded_paths=_EXCLUDED_PATHS,
        sources=_SOURCES,
    )

