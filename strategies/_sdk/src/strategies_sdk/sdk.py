"""The strategy Protocol and manifest validation.

Every field in `manifest().limits` is a `{default, max}` pair (see
`core_py.models.StrategyLimit`). `max` must never exceed the platform
ceiling passed in -- CLAUDE.md invariant #5: limits resolve through three
levels that only tighten (platform ceiling >= strategy max >= request).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from core_py.models import StrategyManifest


@dataclass(frozen=True)
class PlatformCeiling:
    """The hard ceiling no strategy manifest may exceed, per CLAUDE.md."""

    max_usd: float
    max_iterations: int
    max_minutes: int


# CLAUDE.md: "modelar el techo de plataforma como
# {max_usd: 10, max_iterations: 5, max_minutes: 60}".
PLATFORM_CEILING = PlatformCeiling(max_usd=10.0, max_iterations=5, max_minutes=60)


class ManifestValidationError(ValueError):
    """A strategy manifest violates the SDK schema or the platform ceiling."""


@runtime_checkable
class StrategyModule(Protocol):
    """The contract a strategy package under `strategies/<name>/` must
    satisfy: a single `manifest()` callable returning a `StrategyManifest`.
    """

    def manifest(self) -> StrategyManifest: ...


_LIMIT_FIELDS = ("max_usd", "max_iterations", "max_minutes")


def _validate_inputs_schema(inputs: dict[str, Any]) -> list[str]:
    """Validate the JSON-schema-like `inputs` dict.

    Each entry must at minimum declare a `type`. This is intentionally
    permissive (a real JSON Schema validator is out of scope for the
    prototype) but catches the shapes that would silently break a
    strategy's own request-input validation later.
    """

    errors: list[str] = []
    if not isinstance(inputs, dict):
        return ["inputs must be an object"]

    for name, spec in inputs.items():
        if not isinstance(spec, dict):
            errors.append(f"inputs.{name} must be an object describing the field")
            continue
        if "type" not in spec:
            errors.append(f"inputs.{name} is missing 'type'")
        if spec.get("required") and "enum" in spec and not spec["enum"]:
            errors.append(f"inputs.{name} declares an empty enum")

    return errors


def validate_manifest(
    manifest: StrategyManifest,
    ceiling: PlatformCeiling = PLATFORM_CEILING,
) -> None:
    """Raise `ManifestValidationError` if `manifest` is invalid.

    Checks:
    - `inputs` matches the JSON-schema-like shape the SDK expects.
    - every `limits.<field>.max` does not exceed the platform ceiling.
    - every `limits.<field>.default` does not exceed that field's own max.
    - `checks`, `writable_paths` and `sources` are non-empty.
    """

    errors: list[str] = []

    errors.extend(_validate_inputs_schema(manifest.inputs))

    ceiling_values = {
        "max_usd": ceiling.max_usd,
        "max_iterations": ceiling.max_iterations,
        "max_minutes": ceiling.max_minutes,
    }
    for field in _LIMIT_FIELDS:
        limit = getattr(manifest.limits, field)
        ceiling_value = ceiling_values[field]
        if limit.max > ceiling_value:
            errors.append(
                f"limits.{field}.max ({limit.max}) exceeds the platform ceiling "
                f"({ceiling_value})"
            )
        if limit.default > limit.max:
            errors.append(
                f"limits.{field}.default ({limit.default}) exceeds limits.{field}.max "
                f"({limit.max})"
            )

    if not manifest.checks:
        errors.append("checks must declare at least one named check")
    if not manifest.writable_paths:
        errors.append("writable_paths must declare at least one path")
    if not manifest.sources:
        errors.append("sources must cite at least one official source")

    if errors:
        raise ManifestValidationError("; ".join(errors))
