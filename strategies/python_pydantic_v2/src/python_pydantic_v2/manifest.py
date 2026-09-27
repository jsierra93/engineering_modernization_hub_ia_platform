"""Manifest for the `python-pydantic-v2` strategy."""

from __future__ import annotations

from core_py.models import StrategyLimit, StrategyLimits, StrategyManifest

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

_CHECKS = ["install", "unit_tests", "lint"]

# Writable paths intersect with the strategy's own domain: Python source
# and its packaging manifests. CI configuration and infrastructure-as-code
# are excluded even though a glob like **/*.py would otherwise reach them.
_WRITABLE_PATHS = [
    "**/*.py",
    "pyproject.toml",
    "requirements*.txt",
]
_EXCLUDED_PATHS = [
    "**/ci/**",
    "**/*.tf",
]

_SOURCES = ["https://docs.pydantic.dev/latest/migration/"]


def manifest() -> StrategyManifest:
    return StrategyManifest(
        id="python-pydantic-v2",
        version="1.0.0",
        title="Pydantic v1 -> v2",
        applies_to={
            "language": "python",
            "detect": ["pydantic<2 en pyproject.toml o requirements*.txt"],
        },
        inputs=_INPUTS,
        limits=_LIMITS,
        checks=_CHECKS,
        writable_paths=_WRITABLE_PATHS,
        excluded_paths=_EXCLUDED_PATHS,
        sources=_SOURCES,
    )


# Exposed separately from the manifest schema (which has no room for an
# "excluded" list) so the policy gate (Fase 3, task 3.5) can intersect it
# with the request's own restricciones.excluded_paths per CLAUDE.md
# invariant #4 (resolve_scope only tightens).
EXCLUDED_PATHS = _EXCLUDED_PATHS
